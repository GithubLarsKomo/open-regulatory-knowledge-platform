"""Regression tests that generic Core writes cannot bypass governed PER workflows."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orkp.api.main import create_app
from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository


@pytest.fixture
def api_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return TestClient(
        create_app(session_factory_override=session_factory)
    ), session_factory


def _raw_report(session_factory):
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        report, _ = repo.create_object(
            object_type="report",
            payload={"test_only": "generic guard fixture"},
            owner_user_id="report-owner",
            created_by="report-owner",
        )
        repo.session.commit()
        return report.uuid_hex


def test_generic_core_creation_rejects_report_object_type(api_context):
    client, _ = api_context

    response = client.post(
        "/api/v1/objects",
        json={
            "object_type": "report",
            "payload": {"test_only": "must not persist"},
            "owner_user_id": "report-owner",
        },
    )

    assert response.status_code == 409
    assert "domain-specific creation workflow" in response.json()["detail"]


def test_generic_core_versioning_rejects_report(api_context):
    client, session_factory = api_context
    report_uuid = _raw_report(session_factory)

    response = client.post(
        f"/api/v1/objects/{report_uuid}/versions",
        json={
            "payload": {"test_only": "must not create version"},
            "created_by": "report-owner",
        },
    )

    assert response.status_code == 409
    assert "domain-specific versioning workflow" in response.json()["detail"]
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        report = repo.get_by_uuid_hex(report_uuid)
        assert report.current_version == 1


def test_generic_core_submit_rejects_report(api_context):
    client, session_factory = api_context
    report_uuid = _raw_report(session_factory)

    response = client.post(
        f"/api/v1/objects/{report_uuid}/transitions",
        json={"new_state": "in_review", "actor_user_id": "report-owner"},
    )

    assert response.status_code == 409
    assert "domain-specific workflow" in response.json()["detail"]
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        assert repo.get_by_uuid_hex(report_uuid).lifecycle_state == "draft"


def test_generic_core_approval_cannot_bypass_report_four_eyes(api_context):
    client, session_factory = api_context
    report_uuid = _raw_report(session_factory)
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        report = repo.get_by_uuid_hex(report_uuid)
        repo.transition_state(report.object_uuid, "in_review", "report-owner")
        repo.session.commit()

    response = client.post(
        f"/api/v1/objects/{report_uuid}/transitions",
        json={"new_state": "approved", "actor_user_id": "report-owner"},
    )

    assert response.status_code == 409
    assert "domain-specific workflow" in response.json()["detail"]
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        assert repo.get_by_uuid_hex(report_uuid).lifecycle_state == "in_review"


def test_generic_core_report_reads_remain_available(api_context):
    client, session_factory = api_context
    report_uuid = _raw_report(session_factory)

    response = client.get(f"/api/v1/objects/{report_uuid}")

    assert response.status_code == 200
    assert response.json()["object_uuid"] == report_uuid
    assert response.json()["object_type"] == "report"

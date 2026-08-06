"""API tests for reproducible Risk Report baselines."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orkp.api.main import create_app
from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository


@pytest.fixture
def app_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    app = create_app(session_factory_override=session_factory)
    return TestClient(app), session_factory


def _create_object(client, object_type: str, payload: dict):
    response = client.post(
        "/api/v1/objects",
        json={
            "object_type": object_type,
            "payload": payload,
            "owner_user_id": "owner",
        },
    )
    assert response.status_code == 201
    return response.json()["object_uuid"]


def _approve_risk(session_factory, risk_uuid: str):
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        risk = repo.get_by_uuid_hex(risk_uuid)
        repo.transition_state(risk.object_uuid, "in_review", "risk-author")
        repo.transition_state(risk.object_uuid, "approved", "risk-approver")
        session.commit()


def _create_baseline(client, risk_uuid: str, hazard_uuid: str | None = None):
    objects = [{"object_uuid": risk_uuid, "object_version": 1}]
    if hazard_uuid is not None:
        objects.append({"object_uuid": hazard_uuid, "object_version": 1})
    return client.post(
        "/api/v1/risk-report-baselines",
        json={
            "name": "API Risk Report baseline",
            "description": "Frozen API report inputs",
            "objects": objects,
            "created_by_user_id": "report-author",
        },
    )


def test_api_creates_reads_and_generates_risk_report(app_context):
    client, session_factory = app_context
    risk_uuid = _create_object(client, "risk_analysis", {"risk_id": "R-API"})
    hazard_uuid = _create_object(client, "hazard", {"hazard_id": "H-API"})
    _approve_risk(session_factory, risk_uuid)

    created = _create_baseline(client, risk_uuid, hazard_uuid)
    assert created.status_code == 201
    baseline = created.json()
    assert baseline["item_count"] == 2

    fetched = client.get(f"/api/v1/risk-report-baselines/{baseline['baseline_uuid']}")
    assert fetched.status_code == 200
    assert fetched.json() == baseline

    generated = client.post(
        f"/api/v1/risk-report-baselines/{baseline['baseline_uuid']}/reports",
        json={"generated_by_user_id": "report-generator"},
    )
    assert generated.status_code == 201
    body = generated.json()
    assert body["baseline_uuid"] == baseline["baseline_uuid"]
    assert len(body["checksum_sha256"]) == 64
    assert body["format"] == "json"
    assert [item["object_type"] for item in body["report"]["items"]] == [
        "hazard",
        "risk_analysis",
    ]


def test_api_rejects_draft_risk_root(app_context):
    client, _ = app_context
    risk_uuid = _create_object(client, "risk_analysis", {"risk_id": "R-DRAFT"})

    response = _create_baseline(client, risk_uuid)

    assert response.status_code == 422
    assert "approved/effective Risk Analysis" in response.json()["detail"]


def test_api_regeneration_returns_same_canonical_content_and_checksum(app_context):
    client, session_factory = app_context
    risk_uuid = _create_object(client, "risk_analysis", {"risk_id": "R-REPEAT"})
    _approve_risk(session_factory, risk_uuid)
    created = _create_baseline(client, risk_uuid)
    baseline_uuid = created.json()["baseline_uuid"]

    first = client.post(
        f"/api/v1/risk-report-baselines/{baseline_uuid}/reports",
        json={"generated_by_user_id": "generator-one"},
    )
    second = client.post(
        f"/api/v1/risk-report-baselines/{baseline_uuid}/reports",
        json={"generated_by_user_id": "generator-two"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["canonical_json"] == second.json()["canonical_json"]
    assert first.json()["checksum_sha256"] == second.json()["checksum_sha256"]
    assert first.json()["artifact_uuid"] != second.json()["artifact_uuid"]

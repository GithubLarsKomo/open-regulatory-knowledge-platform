"""API tests for Risk Control to Requirement traceability."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orkp.api.main import create_app
from orkp.db.models import Base


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    app = create_app(session_factory_override=session_factory)
    return TestClient(app)


def _create_object(client, object_type: str, identifier: str):
    response = client.post(
        "/api/v1/objects",
        json={
            "object_type": object_type,
            "payload": {"id": identifier},
            "owner_user_id": "owner",
        },
    )
    assert response.status_code == 201
    return response.json()["object_uuid"]


def test_api_links_risk_control_to_requirement(client):
    control_uuid = _create_object(client, "risk_control", "RC-001")
    requirement_uuid = _create_object(client, "requirement", "REQ-001")

    response = client.post(
        f"/api/v1/risk-controls/{control_uuid}/requirements/{requirement_uuid}",
        params={"actor_user_id": "risk-owner"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["relation_type"] == "implements_requirement"
    assert body["risk_control"] == {
        "object_uuid": control_uuid,
        "object_version": 1,
    }
    assert body["requirement"] == {
        "object_uuid": requirement_uuid,
        "object_version": 1,
    }


def test_api_rejects_non_requirement_target(client):
    control_uuid = _create_object(client, "risk_control", "RC-001")
    claim_uuid = _create_object(client, "claim", "CLM-001")

    response = client.post(
        f"/api/v1/risk-controls/{control_uuid}/requirements/{claim_uuid}",
        params={"actor_user_id": "risk-owner"},
    )

    assert response.status_code == 422
    assert "Expected type 'requirement'" in response.json()["detail"]

"""API regressions for structured Performance Studies."""

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
    return TestClient(create_app(session_factory_override=session_factory))


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


def _study_body(product_uuid: str):
    return {
        "study_id": "ST-API-001",
        "study_type": "scientific_validity",
        "title": "Scientific validity study",
        "description": "API-created structured study",
        "product": {"object_uuid": product_uuid, "object_version": 1},
        "study_status": "ongoing",
        "owner_user_id": "study-owner",
    }


def test_api_creates_and_reads_exact_performance_study(client):
    product_uuid = _create_object(client, "product", "P-API")

    created = client.post(
        f"/api/v1/products/{product_uuid}/performance-studies",
        json=_study_body(product_uuid),
    )

    assert created.status_code == 201
    body = created.json()
    assert body["object_version"] == 1
    assert body["lifecycle_state"] == "draft"
    assert body["payload"]["study_type"] == "scientific_validity"
    assert body["payload"]["product"] == {
        "object_uuid": product_uuid,
        "object_version": 1,
    }

    loaded = client.get(
        f"/api/v1/performance-studies/{body['object_uuid']}/versions/1"
    )
    assert loaded.status_code == 200
    assert loaded.json() == body


def test_api_rejects_non_product_study_context(client):
    claim_uuid = _create_object(client, "claim", "C-API")

    response = client.post(
        f"/api/v1/products/{claim_uuid}/performance-studies",
        json=_study_body(claim_uuid),
    )

    assert response.status_code == 422
    assert "Expected type 'product'" in response.json()["detail"]

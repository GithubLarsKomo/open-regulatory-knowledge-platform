"""API regressions for Performance Result evidence."""

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


def _create_study(client, product_uuid: str):
    response = client.post(
        f"/api/v1/products/{product_uuid}/performance-studies",
        json={
            "study_id": "ST-RESULT-API",
            "study_type": "clinical",
            "title": "Clinical performance study",
            "product": {"object_uuid": product_uuid, "object_version": 1},
            "study_status": "completed",
            "owner_user_id": "study-owner",
        },
    )
    assert response.status_code == 201
    return response.json()


def _result_body(study, claim_uuid: str):
    return {
        "result_id": "PR-API-001",
        "study": {
            "object_uuid": study["object_uuid"],
            "object_version": study["object_version"],
        },
        "claims": [{"object_uuid": claim_uuid, "object_version": 1}],
        "parameter": "clinical sensitivity",
        "result_value": "97.4",
        "unit": "%",
        "statistical_method": "Wilson 95% CI",
        "quality_rating": "high",
        "owner_user_id": "result-owner",
    }


def test_api_creates_result_and_exposes_it_as_claim_evidence(client):
    product_uuid = _create_object(client, "product", "P-RESULT-API")
    claim_uuid = _create_object(client, "claim", "C-RESULT-API")
    study = _create_study(client, product_uuid)

    created = client.post(
        f"/api/v1/performance-studies/{study['object_uuid']}/results",
        json=_result_body(study, claim_uuid),
    )

    assert created.status_code == 201
    body = created.json()
    assert body["payload"]["evidence_type"] == "clinical_study"
    assert body["payload"]["claims"] == [
        {"object_uuid": claim_uuid, "object_version": 1}
    ]

    loaded = client.get(
        f"/api/v1/performance-results/{body['object_uuid']}/versions/1"
    )
    assert loaded.status_code == 200
    assert loaded.json() == body

    claim_evidence = client.get(f"/api/v1/claims/{claim_uuid}/evidence")
    assert claim_evidence.status_code == 200
    assert any(
        item["evidence_uuid"] == body["object_uuid"]
        for item in claim_evidence.json()
    )


def test_api_rejects_stale_claim_reference_for_result(client):
    product_uuid = _create_object(client, "product", "P-RESULT-STALE")
    claim_uuid = _create_object(client, "claim", "C-RESULT-STALE")
    study = _create_study(client, product_uuid)

    version = client.post(
        f"/api/v1/objects/{claim_uuid}/versions",
        json={"payload": {"id": "C-RESULT-STALE-v2"}, "created_by": "owner"},
    )
    assert version.status_code == 201

    response = client.post(
        f"/api/v1/performance-studies/{study['object_uuid']}/results",
        json=_result_body(study, claim_uuid),
    )

    assert response.status_code == 422
    assert "current Claim versions" in response.json()["detail"]

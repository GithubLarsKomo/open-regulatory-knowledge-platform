"""API regressions for statistical Performance Result provenance."""

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


def _create_study(client, product_uuid: str):
    response = client.post(
        f"/api/v1/products/{product_uuid}/performance-studies",
        json={
            "study_id": "ST-STATS-API",
            "study_type": "analytical",
            "title": "Analytical performance study",
            "product": {"object_uuid": product_uuid, "object_version": 1},
            "study_status": "completed",
            "owner_user_id": "study-owner",
        },
    )
    assert response.status_code == 201
    return response.json()


def _body(study, claim_uuid: str, source_uuid: str | None):
    body = {
        "result_id": "PR-STATS-API",
        "study": {"object_uuid": study["object_uuid"], "object_version": 1},
        "claims": [{"object_uuid": claim_uuid, "object_version": 1}],
        "parameter": "specificity",
        "result_value": "99.1",
        "unit": "%",
        "statistical_method": "Wilson 95% CI",
        "quality_rating": "high",
        "owner_user_id": "result-owner",
    }
    if source_uuid is not None:
        body["statistical_sources"] = [
            {
                "source_kind": "source_data",
                "evidence": {"object_uuid": source_uuid, "object_version": 1},
            }
        ]
    return body


def test_api_creates_statistical_result_with_source_data(client):
    product_uuid = _create_object(client, "product", {"id": "P-STATS-API"})
    claim_uuid = _create_object(client, "claim", {"id": "C-STATS-API"})
    source_uuid = _create_object(
        client,
        "evidence",
        {"evidence_type": "internal_document", "title": "Raw locked dataset"},
    )
    study = _create_study(client, product_uuid)

    response = client.post(
        f"/api/v1/performance-studies/{study['object_uuid']}/results",
        json=_body(study, claim_uuid, source_uuid),
    )

    assert response.status_code == 201
    payload = response.json()["payload"]
    assert payload["statistical_method"] == "Wilson 95% CI"
    assert payload["statistical_sources"] == [
        {
            "source_kind": "source_data",
            "evidence": {"object_uuid": source_uuid, "object_version": 1},
        }
    ]


def test_api_rejects_statistical_result_without_source(client):
    product_uuid = _create_object(client, "product", {"id": "P-NO-SOURCE"})
    claim_uuid = _create_object(client, "claim", {"id": "C-NO-SOURCE"})
    study = _create_study(client, product_uuid)

    response = client.post(
        f"/api/v1/performance-studies/{study['object_uuid']}/results",
        json=_body(study, claim_uuid, None),
    )

    assert response.status_code == 422
    assert "statistical_sources are required" in response.text

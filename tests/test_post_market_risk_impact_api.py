"""API tests for post-market safety information and Risk Impact Assessment."""

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


def _create_risk(client):
    response = client.post(
        "/api/v1/objects",
        json={
            "object_type": "risk_analysis",
            "payload": {"risk_id": "R-API-PMS", "title": "API post-market risk"},
            "owner_user_id": "risk-owner",
        },
    )
    assert response.status_code == 201
    return response.json()


def _ingestion_body(risk):
    return {
        "risk_analysis": {
            "object_uuid": risk["object_uuid"],
            "object_version": risk["current_version"],
        },
        "source_type": "complaint",
        "title": "Unexpected false-negative complaint",
        "description": "A complaint reports an unexpected false-negative result.",
        "observed_at": "2026-08-05T10:00:00+00:00",
        "reported_by_user_id": "safety-reporter",
        "external_reference": "CMP-API-001",
    }


def _ingest(client):
    risk = _create_risk(client)
    response = client.post(
        f"/api/v1/risk-analyses/{risk['object_uuid']}/post-market-information",
        json=_ingestion_body(risk),
    )
    assert response.status_code == 201
    return risk, response.json()


def test_ingestion_returns_pending_assessment_and_exact_gets(client):
    _, result = _ingest(client)

    information = result["information"]
    assessment = result["impact_assessment"]
    assert assessment["object_version"] == 1
    assert assessment["payload"]["outcome"] == "pending"
    assert assessment["payload"]["requires_risk_review"] is True

    information_get = client.get(
        f"/api/v1/post-market-information/{information['object_uuid']}/versions/1"
    )
    assessment_get = client.get(
        f"/api/v1/risk-impact-assessments/{assessment['object_uuid']}/versions/1"
    )

    assert information_get.status_code == 200
    assert information_get.json()["payload"]["information_id"].startswith("pmi-")
    assert assessment_get.status_code == 200
    assert assessment_get.json()["payload"]["assessment_id"].startswith("ria-")


def test_stale_risk_version_is_rejected_for_ingestion(client):
    risk = _create_risk(client)
    body = _ingestion_body(risk)

    version_response = client.post(
        f"/api/v1/objects/{risk['object_uuid']}/versions",
        json={
            "payload": {"risk_id": "R-API-PMS", "title": "API post-market risk v2"},
            "created_by": "risk-owner",
        },
    )
    assert version_response.status_code == 201

    response = client.post(
        f"/api/v1/risk-analyses/{risk['object_uuid']}/post-market-information",
        json=body,
    )

    assert response.status_code == 422
    assert "current Risk Analysis version" in response.json()["detail"]


def test_pending_assessment_cannot_be_submitted_for_review(client):
    _, result = _ingest(client)
    assessment_uuid = result["impact_assessment"]["object_uuid"]

    response = client.post(
        f"/api/v1/risk-impact-assessments/{assessment_uuid}/transitions/in_review",
        params={"actor_user_id": "risk-assessor"},
    )

    assert response.status_code == 422
    assert "completed before review" in response.json()["detail"]


def test_generic_lifecycle_cannot_bypass_pending_review_gate(client):
    _, result = _ingest(client)
    assessment_uuid = result["impact_assessment"]["object_uuid"]

    response = client.post(
        f"/api/v1/objects/{assessment_uuid}/transitions",
        json={"new_state": "in_review", "actor_user_id": "risk-assessor"},
    )

    assert response.status_code == 409
    assert "domain-specific workflow" in response.json()["detail"]


def test_complete_review_and_independent_approval(client):
    _, result = _ingest(client)
    assessment_uuid = result["impact_assessment"]["object_uuid"]

    completed = client.post(
        f"/api/v1/risk-impact-assessments/{assessment_uuid}/complete",
        json={
            "outcome": "no_change",
            "rationale": "The information is already covered by the current risk estimate.",
            "assessor_user_id": "risk-assessor",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["object_version"] == 2
    assert completed.json()["payload"]["requires_risk_review"] is False

    submitted = client.post(
        f"/api/v1/risk-impact-assessments/{assessment_uuid}/transitions/in_review",
        params={"actor_user_id": "risk-assessor"},
    )
    assert submitted.status_code == 200

    approved = client.post(
        f"/api/v1/risk-impact-assessments/{assessment_uuid}/transitions/approved",
        params={"actor_user_id": "risk-approver"},
    )

    assert approved.status_code == 200
    assert approved.json()["lifecycle_state"] == "approved"
    assert approved.json()["object_version"] == 2


def test_assessor_cannot_self_approve_via_specialized_api(client):
    _, result = _ingest(client)
    assessment_uuid = result["impact_assessment"]["object_uuid"]

    completed = client.post(
        f"/api/v1/risk-impact-assessments/{assessment_uuid}/complete",
        json={
            "outcome": "review_required",
            "rationale": "The complaint requires formal risk review.",
            "assessor_user_id": "risk-assessor",
        },
    )
    assert completed.status_code == 200

    submitted = client.post(
        f"/api/v1/risk-impact-assessments/{assessment_uuid}/transitions/in_review",
        params={"actor_user_id": "risk-assessor"},
    )
    assert submitted.status_code == 200

    approved = client.post(
        f"/api/v1/risk-impact-assessments/{assessment_uuid}/transitions/approved",
        params={"actor_user_id": "risk-assessor"},
    )

    assert approved.status_code == 403
    assert "cannot approve their own assessment" in approved.json()["detail"]

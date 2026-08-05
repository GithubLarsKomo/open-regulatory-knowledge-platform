"""API tests for version-pinned Benefit-Risk Analysis."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orkp.api.main import create_app
from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository


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
    app.state.test_session_factory = session_factory
    return TestClient(app)


def _policy_payload():
    severity = ["negligible", "minor", "moderate", "critical", "catastrophic"]
    probability = ["improbable", "unlikely", "possible", "likely", "probable"]
    return {
        "policy_id": "POL-API",
        "name": "API Benefit-Risk Policy",
        "policy_version": "1.0",
        "severity_scale": severity,
        "probability_scale": probability,
        "risk_levels": ["high"],
        "risk_matrix": {
            sev: {prob: "high" for prob in probability} for sev in severity
        },
        "acceptability_rules": {"high": False},
        "required_actions": {"high": "benefit_risk_required"},
        "control_hierarchy": [
            "design_by_safety",
            "protective_measure",
            "information_for_safety",
        ],
        "benefit_risk_required_for": ["high"],
    }


def _seed_context(client, *, acceptable=False, benefit_risk_required=True):
    session_factory = client.app.state.test_session_factory
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        risk_analysis, _ = repo.create_object(
            "risk_analysis",
            {"risk_id": "R-API", "title": "API risk"},
            "owner",
            "owner",
        )
        risk_policy, _ = repo.create_object(
            "risk_policy",
            _policy_payload(),
            "owner",
            "owner",
        )
        repo.transition_state(risk_policy.object_uuid, "in_review", "owner")
        repo.transition_state(risk_policy.object_uuid, "approved", "approver")
        repo.transition_state(risk_policy.object_uuid, "effective", "owner")

        residual, _ = repo.create_object(
            "residual_risk_evaluation",
            {
                "evaluation_id": "rre-api",
                "risk_analysis_uuid": risk_analysis.uuid_hex,
                "risk_analysis_version": 1,
                "initial_evaluation_uuid": uuid4().hex,
                "initial_evaluation_version": 1,
                "control_verifications": [
                    {"object_uuid": uuid4().hex, "object_version": 1}
                ],
                "residual_severity": "critical",
                "residual_probability": "possible",
                "calculated_risk_level": "high",
                "acceptable": acceptable,
                "action_required": "benefit_risk_required",
                "severity_improved": False,
                "probability_improved": True,
                "severity_worsened": False,
                "probability_worsened": False,
                "risk_level_improved": True,
                "reduced": True,
                "regression_detected": False,
                "benefit_risk_required": benefit_risk_required,
                "risk_policy_uuid": risk_policy.uuid_hex,
                "risk_policy_version": 1,
                "policy_revision": "1.0",
                "evaluator_user_id": "owner",
                "rationale": "Residual risk remains high.",
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
            },
            "owner",
            "owner",
        )
        repo.create_relation(
            source_uuid=residual.object_uuid,
            source_version=1,
            target_uuid=risk_analysis.object_uuid,
            target_version=1,
            relation_type="residual_of",
            created_by="owner",
        )
        repo.create_relation(
            source_uuid=residual.object_uuid,
            source_version=1,
            target_uuid=risk_policy.object_uuid,
            target_version=1,
            relation_type="uses_risk_policy",
            created_by="owner",
        )
        session.commit()
        return risk_analysis.uuid_hex, risk_policy.uuid_hex, residual.uuid_hex


def _body(risk_analysis_uuid, risk_policy_uuid, residual_uuid):
    return {
        "residual_evaluation": {
            "object_uuid": residual_uuid,
            "object_version": 1,
        },
        "risk_analysis": {
            "object_uuid": risk_analysis_uuid,
            "object_version": 1,
        },
        "risk_policy": {
            "object_uuid": risk_policy_uuid,
            "object_version": 1,
        },
        "benefits": "Clinical benefit outweighs remaining risk.",
        "residual_risks": "A high residual risk remains.",
        "rationale": "Benefit is clinically meaningful and alternatives are limited.",
        "conclusion": "favorable",
        "evaluator_user_id": "reviewer",
    }


def test_create_and_get_benefit_risk_analysis(client):
    risk_uuid, policy_uuid, residual_uuid = _seed_context(client)
    response = client.post(
        f"/api/v1/residual-risk-evaluations/{residual_uuid}/benefit-risk-analyses",
        json=_body(risk_uuid, policy_uuid, residual_uuid),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["lifecycle_state"] == "draft"
    assert data["payload"]["analysis_id"].startswith("bra-")

    fetched = client.get(
        f"/api/v1/benefit-risk-analyses/{data['object_uuid']}/versions/1"
    )
    assert fetched.status_code == 200
    assert fetched.json()["payload"]["conclusion"] == "favorable"


def test_acceptable_residual_returns_422(client):
    risk_uuid, policy_uuid, residual_uuid = _seed_context(
        client,
        acceptable=True,
        benefit_risk_required=False,
    )
    response = client.post(
        f"/api/v1/residual-risk-evaluations/{residual_uuid}/benefit-risk-analyses",
        json=_body(risk_uuid, policy_uuid, residual_uuid),
    )

    assert response.status_code == 422


def test_creator_self_approval_returns_403(client):
    risk_uuid, policy_uuid, residual_uuid = _seed_context(client)
    created = client.post(
        f"/api/v1/residual-risk-evaluations/{residual_uuid}/benefit-risk-analyses",
        json=_body(risk_uuid, policy_uuid, residual_uuid),
    )
    assert created.status_code == 201
    analysis_uuid = created.json()["object_uuid"]

    submitted = client.post(
        f"/api/v1/benefit-risk-analyses/{analysis_uuid}/transitions/in_review",
        params={"actor_user_id": "reviewer"},
    )
    assert submitted.status_code == 200

    approval = client.post(
        f"/api/v1/benefit-risk-analyses/{analysis_uuid}/transitions/approved",
        params={"actor_user_id": "reviewer"},
    )
    assert approval.status_code == 403

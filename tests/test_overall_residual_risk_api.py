"""API tests for product-level Overall Residual Risk evaluation."""

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
        "policy_id": "POL-ORR-API",
        "name": "Overall Residual Risk API Policy",
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


def _seed_context(client):
    session_factory = client.app.state.test_session_factory
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        product, _ = repo.create_object(
            "product",
            {"product_id": "P-ORR-API", "name": "Overall API Product"},
            "product-owner",
            "product-owner",
        )
        risk, _ = repo.create_object(
            "risk_analysis",
            {"risk_id": "R-ORR-API", "title": "Overall API risk"},
            "risk-owner",
            "risk-owner",
        )
        repo.transition_state(risk.object_uuid, "in_review", "risk-owner")
        repo.transition_state(risk.object_uuid, "approved", "risk-approver")

        policy, _ = repo.create_object(
            "risk_policy",
            _policy_payload(),
            "policy-owner",
            "policy-owner",
        )
        repo.transition_state(policy.object_uuid, "in_review", "policy-owner")
        repo.transition_state(policy.object_uuid, "approved", "policy-approver")
        repo.transition_state(policy.object_uuid, "effective", "policy-owner")

        repo.create_relation(
            source_uuid=product.object_uuid,
            source_version=1,
            target_uuid=risk.object_uuid,
            target_version=1,
            relation_type="has_risk",
            created_by="product-owner",
        )

        residual, _ = repo.create_object(
            "residual_risk_evaluation",
            {
                "evaluation_id": "rre-orr-api",
                "risk_analysis_uuid": risk.uuid_hex,
                "risk_analysis_version": 1,
                "initial_evaluation_uuid": uuid4().hex,
                "initial_evaluation_version": 1,
                "control_verifications": [
                    {"object_uuid": uuid4().hex, "object_version": 1}
                ],
                "residual_severity": "critical",
                "residual_probability": "possible",
                "calculated_risk_level": "high",
                "acceptable": True,
                "action_required": "none",
                "severity_improved": False,
                "probability_improved": True,
                "severity_worsened": False,
                "probability_worsened": False,
                "risk_level_improved": True,
                "reduced": True,
                "regression_detected": False,
                "benefit_risk_required": False,
                "risk_policy_uuid": policy.uuid_hex,
                "risk_policy_version": 1,
                "policy_revision": "1.0",
                "evaluator_user_id": "risk-evaluator",
                "rationale": "Residual risk is acceptable.",
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
            },
            "risk-evaluator",
            "risk-evaluator",
        )
        repo.create_relation(
            source_uuid=residual.object_uuid,
            source_version=1,
            target_uuid=risk.object_uuid,
            target_version=1,
            relation_type="residual_of",
            created_by="risk-evaluator",
        )
        session.commit()
        return product.uuid_hex


def _body(product_uuid):
    return {
        "product": {"object_uuid": product_uuid, "object_version": 1},
        "acceptable": True,
        "rationale": "All residual risks were evaluated together.",
        "evaluator_user_id": "overall-reviewer",
    }


def test_create_and_get_overall_residual_risk(client):
    product_uuid = _seed_context(client)

    created = client.post(
        f"/api/v1/products/{product_uuid}/overall-residual-risk-evaluations",
        json=_body(product_uuid),
    )

    assert created.status_code == 201
    data = created.json()
    assert data["lifecycle_state"] == "draft"
    assert data["payload"]["acceptable"] is True
    assert len(data["payload"]["entries"]) == 1

    fetched = client.get(
        f"/api/v1/overall-residual-risk-evaluations/{data['object_uuid']}/versions/1"
    )
    assert fetched.status_code == 200
    assert fetched.json()["payload"]["evaluation_id"].startswith("orr-")


def test_creator_self_approval_returns_403(client):
    product_uuid = _seed_context(client)
    created = client.post(
        f"/api/v1/products/{product_uuid}/overall-residual-risk-evaluations",
        json=_body(product_uuid),
    )
    assert created.status_code == 201
    evaluation_uuid = created.json()["object_uuid"]

    submitted = client.post(
        f"/api/v1/overall-residual-risk-evaluations/{evaluation_uuid}/transitions/in_review",
        params={"actor_user_id": "overall-reviewer"},
    )
    assert submitted.status_code == 200

    approval = client.post(
        f"/api/v1/overall-residual-risk-evaluations/{evaluation_uuid}/transitions/approved",
        params={"actor_user_id": "overall-reviewer"},
    )
    assert approval.status_code == 403


def test_generic_approval_cannot_bypass_overall_risk_workflow(client):
    product_uuid = _seed_context(client)
    created = client.post(
        f"/api/v1/products/{product_uuid}/overall-residual-risk-evaluations",
        json=_body(product_uuid),
    )
    assert created.status_code == 201
    evaluation_uuid = created.json()["object_uuid"]

    submitted = client.post(
        f"/api/v1/overall-residual-risk-evaluations/{evaluation_uuid}/transitions/in_review",
        params={"actor_user_id": "overall-reviewer"},
    )
    assert submitted.status_code == 200

    generic = client.post(
        f"/api/v1/objects/{evaluation_uuid}/transitions",
        json={"new_state": "approved", "actor_user_id": "other-user"},
    )
    assert generic.status_code == 409


def test_product_without_approved_risks_returns_422(client):
    response = client.post(
        "/api/v1/objects",
        json={
            "object_type": "product",
            "payload": {"product_id": "P-NO-RISK", "name": "No risk product"},
            "owner_user_id": "owner",
        },
    )
    assert response.status_code == 201
    product_uuid = response.json()["object_uuid"]

    created = client.post(
        f"/api/v1/products/{product_uuid}/overall-residual-risk-evaluations",
        json=_body(product_uuid),
    )
    assert created.status_code == 422

"""Regression tests for domain-governed lifecycle transition guards."""

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


def _create_object(client, object_type):
    response = client.post(
        "/api/v1/objects",
        json={
            "object_type": object_type,
            "payload": {"test": True},
            "owner_user_id": "owner",
        },
    )
    assert response.status_code == 201
    return response.json()["object_uuid"]


@pytest.mark.parametrize(
    "object_type",
    [
        "product",
        "claim",
        "evidence",
        "risk_analysis",
        "control_verification",
        "benefit_risk",
    ],
)
def test_generic_approval_is_blocked_for_governed_object_types(client, object_type):
    object_uuid = _create_object(client, object_type)
    submitted = client.post(
        f"/api/v1/objects/{object_uuid}/transitions",
        json={"new_state": "in_review", "actor_user_id": "owner"},
    )
    assert submitted.status_code == 200

    approved = client.post(
        f"/api/v1/objects/{object_uuid}/transitions",
        json={"new_state": "approved", "actor_user_id": "owner"},
    )

    assert approved.status_code == 409
    assert "domain-specific workflow" in approved.json()["detail"]


def test_generic_effective_transition_is_blocked_for_control_verification(client):
    session_factory = client.app.state.test_session_factory
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        verification, _ = repo.create_object(
            "control_verification",
            {"test": True},
            "owner",
            "owner",
        )
        repo.transition_state(verification.object_uuid, "in_review", "owner")
        repo.transition_state(verification.object_uuid, "approved", "approver")
        session.commit()
        verification_uuid = verification.uuid_hex

    response = client.post(
        f"/api/v1/objects/{verification_uuid}/transitions",
        json={"new_state": "effective", "actor_user_id": "owner"},
    )

    assert response.status_code == 409
    assert "domain-specific workflow" in response.json()["detail"]


def test_specialized_risk_approval_runs_completeness_gate(client):
    risk_uuid = _create_object(client, "risk_analysis")
    submitted = client.post(
        f"/api/v1/risk-analyses/{risk_uuid}/submit",
        params={"actor_user_id": "owner"},
    )
    assert submitted.status_code == 200

    approval = client.post(
        f"/api/v1/risk-analyses/{risk_uuid}/approve",
        params={"actor_user_id": "approver"},
    )

    assert approval.status_code == 422
    assert "Risk approval blocked" in approval.json()["detail"]


def test_ungoverned_risk_policy_can_use_generic_approval(client):
    policy_uuid = _create_object(client, "risk_policy")
    submitted = client.post(
        f"/api/v1/objects/{policy_uuid}/transitions",
        json={"new_state": "in_review", "actor_user_id": "owner"},
    )
    assert submitted.status_code == 200

    approved = client.post(
        f"/api/v1/objects/{policy_uuid}/transitions",
        json={"new_state": "approved", "actor_user_id": "approver"},
    )

    assert approved.status_code == 200
    assert approved.json()["lifecycle_state"] == "approved"

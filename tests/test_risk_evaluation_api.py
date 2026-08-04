"""Tests for the Risk Evaluation API endpoints via TestClient."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from orkp.api.main import create_app
from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.control_verification_service import ControlVerificationService
from orkp.domain.risk_models import ControlVerificationCreateRequest


@pytest.fixture(scope="function")
def client():
    """Create a test client with in-memory SQLite."""
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)

    app = create_app(session_factory_override=test_session)
    app.state.test_session_factory = test_session
    return TestClient(app)


def _create_policy(client, lifecycle_state="effective"):
    payload = {
        "policy_id": "POL-001",
        "name": "Test Policy",
        "policy_version": "1.0",
        "severity_scale": [
            "negligible",
            "minor",
            "moderate",
            "critical",
            "catastrophic",
        ],
        "probability_scale": [
            "improbable",
            "unlikely",
            "possible",
            "likely",
            "probable",
        ],
        "risk_levels": ["low", "medium", "high", "intolerable"],
        "risk_matrix": {
            "catastrophic": {
                "improbable": "high",
                "unlikely": "high",
                "possible": "intolerable",
                "likely": "intolerable",
                "probable": "intolerable",
            },
            "critical": {
                "improbable": "medium",
                "unlikely": "high",
                "possible": "high",
                "likely": "intolerable",
                "probable": "intolerable",
            },
            "moderate": {
                "improbable": "medium",
                "unlikely": "medium",
                "possible": "high",
                "likely": "high",
                "probable": "intolerable",
            },
            "minor": {
                "improbable": "low",
                "unlikely": "medium",
                "possible": "medium",
                "likely": "high",
                "probable": "high",
            },
            "negligible": {
                "improbable": "low",
                "unlikely": "low",
                "possible": "medium",
                "likely": "medium",
                "probable": "high",
            },
        },
        "acceptability_rules": {
            "low": True,
            "medium": True,
            "high": False,
            "intolerable": False,
        },
        "required_actions": {
            "low": "none",
            "medium": "monitor",
            "high": "control_required",
            "intolerable": "prohibited",
        },
        "control_hierarchy": [
            "design_by_safety",
            "protective_measure",
            "information_for_safety",
        ],
        "benefit_risk_required_for": ["high", "intolerable"],
    }
    resp = client.post(
        "/api/v1/objects",
        json={
            "object_type": "risk_policy",
            "payload": payload,
            "owner_user_id": "u1",
        },
    )
    assert resp.status_code == 201
    policy_uuid = resp.json()["object_uuid"]

    for state, actor in (("in_review", "u1"), ("approved", "u2")):
        transition = client.post(
            f"/api/v1/objects/{policy_uuid}/transitions",
            json={"new_state": state, "actor_user_id": actor},
        )
        assert transition.status_code == 200
    if lifecycle_state == "effective":
        transition = client.post(
            f"/api/v1/objects/{policy_uuid}/transitions",
            json={"new_state": "effective", "actor_user_id": "u1"},
        )
        assert transition.status_code == 200
    return policy_uuid


def _create_risk_analysis(client, owner="u1"):
    resp = client.post(
        "/api/v1/objects",
        json={
            "object_type": "risk_analysis",
            "payload": {
                "risk_id": "R1",
                "title": "Test Risk",
                "severity": "moderate",
                "probability": "possible",
            },
            "owner_user_id": owner,
        },
    )
    assert resp.status_code == 201
    return resp.json()["object_uuid"]


def _dummy_verification_ref():
    return {"object_uuid": uuid.uuid4().hex, "object_version": 1}


def _create_effective_control_verification(
    client,
    risk_analysis_uuid,
    initial_evaluation,
    policy_uuid,
):
    """Seed a real effective control verification using the shared test DB."""
    session_factory = client.app.state.test_session_factory
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        risk_analysis = repo.get_by_uuid_hex(risk_analysis_uuid)
        assert risk_analysis is not None

        risk_control, _ = repo.create_object(
            "risk_control",
            {
                "control_id": f"RC-{uuid.uuid4().hex[:8]}",
                "description": "API test control",
            },
            "u1",
            "u1",
        )
        repo.create_relation(
            source_uuid=risk_analysis.object_uuid,
            source_version=1,
            target_uuid=risk_control.object_uuid,
            target_version=1,
            relation_type="controlled_by",
            created_by="u1",
        )

        evidence, _ = repo.create_object(
            "evidence",
            {
                "evidence_id": f"EV-{uuid.uuid4().hex[:8]}",
                "summary": "API verification evidence",
            },
            "u1",
            "u1",
        )
        repo.transition_state(evidence.object_uuid, "in_review", "u1")
        repo.transition_state(evidence.object_uuid, "approved", "u2")
        repo.transition_state(evidence.object_uuid, "effective", "u1")
        session.commit()

        service = ControlVerificationService(repo)
        verification = service.create_verification(
            risk_control.uuid_hex,
            ControlVerificationCreateRequest(
                risk_analysis={
                    "object_uuid": risk_analysis_uuid,
                    "object_version": 1,
                },
                risk_control={
                    "object_uuid": risk_control.uuid_hex,
                    "object_version": 1,
                },
                initial_evaluation={
                    "object_uuid": initial_evaluation["object_uuid"],
                    "object_version": 1,
                },
                risk_policy={"object_uuid": policy_uuid, "object_version": 1},
                evidence=[
                    {"object_uuid": evidence.uuid_hex, "object_version": 1}
                ],
                verification_method="test",
                verification_scope="Implementation and effectiveness",
                implementation_verified=True,
                effectiveness_verified=True,
                no_new_uncontrolled_risks=True,
                effectiveness_result="effective",
                conclusion="passed",
                verified_by_user_id="u1",
            ),
        )
        service.transition_state(verification.object_uuid, "in_review", "u1")
        service.transition_state(verification.object_uuid, "approved", "u2")
        verification = service.transition_state(
            verification.object_uuid, "effective", "u1"
        )
        assert verification.eligible_for_residual_evaluation is True
        return {
            "object_uuid": verification.object_uuid,
            "object_version": verification.object_version,
        }


class TestInitialEvaluationAPI:
    def test_create_initial_evaluation(self, client):
        ra_uuid = _create_risk_analysis(client)
        pol_uuid = _create_policy(client)

        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/initial-evaluations",
            json={
                "risk_analysis_version": 1,
                "risk_policy_uuid": pol_uuid,
                "risk_policy_version": 1,
                "severity": "moderate",
                "probability": "possible",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["object_version"] == 1
        assert data["lifecycle_state"] == "draft"
        payload = data["payload"]
        assert payload["calculated_risk_level"] == "high"
        assert payload["acceptable"] is False
        assert payload["action_required"] == "control_required"
        assert payload["risk_analysis_version"] == 1
        assert payload["risk_policy_version"] == 1

    def test_get_initial_evaluation(self, client):
        ra_uuid = _create_risk_analysis(client)
        pol_uuid = _create_policy(client)
        create_resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/initial-evaluations",
            json={
                "risk_analysis_version": 1,
                "risk_policy_uuid": pol_uuid,
                "risk_policy_version": 1,
                "severity": "moderate",
                "probability": "possible",
                "evaluator_user_id": "u1",
            },
        )
        assert create_resp.status_code == 201
        object_uuid = create_resp.json()["object_uuid"]

        get_resp = client.get(
            f"/api/v1/initial-risk-evaluations/{object_uuid}/versions/1"
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["object_uuid"] == object_uuid
        assert data["payload"]["calculated_risk_level"] == "high"

    def test_get_nonexistent_initial_evaluation(self, client):
        resp = client.get(
            f"/api/v1/initial-risk-evaluations/{uuid.uuid4().hex}/versions/1"
        )
        assert resp.status_code == 404

    def test_create_initial_missing_policy_returns_404(self, client):
        ra_uuid = _create_risk_analysis(client)
        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/initial-evaluations",
            json={
                "risk_analysis_version": 1,
                "risk_policy_uuid": uuid.uuid4().hex,
                "risk_policy_version": 1,
                "severity": "moderate",
                "probability": "possible",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 404

    def test_create_initial_wrong_ra_version_returns_404(self, client):
        ra_uuid = _create_risk_analysis(client)
        pol_uuid = _create_policy(client)
        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/initial-evaluations",
            json={
                "risk_analysis_version": 999,
                "risk_policy_uuid": pol_uuid,
                "risk_policy_version": 1,
                "severity": "moderate",
                "probability": "possible",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 404

    def test_create_initial_invalid_payload_returns_422(self, client):
        ra_uuid = _create_risk_analysis(client)
        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/initial-evaluations",
            json={
                "risk_analysis_version": 1,
                "risk_policy_uuid": "not-a-uuid",
                "risk_policy_version": 1,
                "severity": "nonexistent",
                "probability": "possible",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 422


class TestResidualEvaluationAPI:
    def _create_initial_evaluation(self, client, ra_uuid, pol_uuid):
        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/initial-evaluations",
            json={
                "risk_analysis_version": 1,
                "risk_policy_uuid": pol_uuid,
                "risk_policy_version": 1,
                "severity": "moderate",
                "probability": "possible",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 201
        return resp.json()

    def test_create_residual_evaluation(self, client):
        ra_uuid = _create_risk_analysis(client)
        pol_uuid = _create_policy(client)
        ie = self._create_initial_evaluation(client, ra_uuid, pol_uuid)
        verification = _create_effective_control_verification(
            client, ra_uuid, ie, pol_uuid
        )

        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/residual-evaluations",
            json={
                "risk_analysis_version": 1,
                "initial_evaluation_uuid": ie["object_uuid"],
                "initial_evaluation_version": 1,
                "control_verifications": [verification],
                "residual_severity": "minor",
                "residual_probability": "unlikely",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["object_version"] == 1
        assert data["lifecycle_state"] == "draft"
        payload = data["payload"]
        assert payload["control_verifications"][0] == verification
        assert payload["calculated_risk_level"] == "medium"
        assert payload["acceptable"] is True
        assert payload["severity_improved"] is True
        assert payload["probability_improved"] is True
        assert payload["reduced"] is True
        assert payload["regression_detected"] is False

    def test_get_residual_evaluation(self, client):
        ra_uuid = _create_risk_analysis(client)
        pol_uuid = _create_policy(client)
        ie = self._create_initial_evaluation(client, ra_uuid, pol_uuid)
        verification = _create_effective_control_verification(
            client, ra_uuid, ie, pol_uuid
        )

        create_resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/residual-evaluations",
            json={
                "risk_analysis_version": 1,
                "initial_evaluation_uuid": ie["object_uuid"],
                "initial_evaluation_version": 1,
                "control_verifications": [verification],
                "residual_severity": "minor",
                "residual_probability": "unlikely",
                "evaluator_user_id": "u1",
            },
        )
        assert create_resp.status_code == 201
        object_uuid = create_resp.json()["object_uuid"]

        get_resp = client.get(
            f"/api/v1/residual-risk-evaluations/{object_uuid}/versions/1"
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["object_uuid"] == object_uuid
        assert data["payload"]["calculated_risk_level"] == "medium"

    def test_get_nonexistent_residual_evaluation(self, client):
        resp = client.get(
            f"/api/v1/residual-risk-evaluations/{uuid.uuid4().hex}/versions/1"
        )
        assert resp.status_code == 404

    def test_create_residual_requires_control_verification(self, client):
        ra_uuid = _create_risk_analysis(client)
        pol_uuid = _create_policy(client)
        ie = self._create_initial_evaluation(client, ra_uuid, pol_uuid)

        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/residual-evaluations",
            json={
                "risk_analysis_version": 1,
                "initial_evaluation_uuid": ie["object_uuid"],
                "initial_evaluation_version": 1,
                "residual_severity": "minor",
                "residual_probability": "unlikely",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 422

    def test_create_residual_missing_initial_returns_404(self, client):
        ra_uuid = _create_risk_analysis(client)
        _create_policy(client)
        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/residual-evaluations",
            json={
                "risk_analysis_version": 1,
                "initial_evaluation_uuid": uuid.uuid4().hex,
                "initial_evaluation_version": 1,
                "control_verifications": [_dummy_verification_ref()],
                "residual_severity": "minor",
                "residual_probability": "unlikely",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 404

    def test_create_residual_wrong_ra_version_returns_404(self, client):
        ra_uuid = _create_risk_analysis(client)
        pol_uuid = _create_policy(client)
        ie = self._create_initial_evaluation(client, ra_uuid, pol_uuid)
        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/residual-evaluations",
            json={
                "risk_analysis_version": 999,
                "initial_evaluation_uuid": ie["object_uuid"],
                "initial_evaluation_version": 1,
                "control_verifications": [_dummy_verification_ref()],
                "residual_severity": "minor",
                "residual_probability": "unlikely",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 404

    def test_create_residual_invalid_severity_returns_422(self, client):
        ra_uuid = _create_risk_analysis(client)
        pol_uuid = _create_policy(client)
        ie = self._create_initial_evaluation(client, ra_uuid, pol_uuid)
        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/residual-evaluations",
            json={
                "risk_analysis_version": 1,
                "initial_evaluation_uuid": ie["object_uuid"],
                "initial_evaluation_version": 1,
                "control_verifications": [_dummy_verification_ref()],
                "residual_severity": "nonexistent",
                "residual_probability": "unlikely",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 422

    def test_residual_regression_detected(self, client):
        ra_uuid = _create_risk_analysis(client)
        pol_uuid = _create_policy(client)
        ie = self._create_initial_evaluation(client, ra_uuid, pol_uuid)
        verification = _create_effective_control_verification(
            client, ra_uuid, ie, pol_uuid
        )

        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/residual-evaluations",
            json={
                "risk_analysis_version": 1,
                "initial_evaluation_uuid": ie["object_uuid"],
                "initial_evaluation_version": 1,
                "control_verifications": [verification],
                "residual_severity": "critical",
                "residual_probability": "probable",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 201
        payload = resp.json()["payload"]
        assert payload["regression_detected"] is True
        assert payload["severity_worsened"] is True
        assert payload["probability_worsened"] is True
        assert payload["reduced"] is False
        assert payload["calculated_risk_level"] == "intolerable"

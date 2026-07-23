"""Tests for the Risk Evaluation API endpoints via TestClient."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from orkp.api.main import create_app
from orkp.db.models import Base


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
    TestSession = sessionmaker(bind=engine)

    app = create_app(session_factory_override=TestSession)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper: seed a risk policy via raw API
# ---------------------------------------------------------------------------


def _create_policy(client, lifecycle_state="effective"):
    """Create and transition a risk policy via API."""
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

    # Transition to effective
    trans = client.post(
        f"/api/v1/objects/{policy_uuid}/transitions",
        json={"new_state": "in_review", "actor_user_id": "u1"},
    )
    assert trans.status_code == 200
    trans = client.post(
        f"/api/v1/objects/{policy_uuid}/transitions",
        json={"new_state": "approved", "actor_user_id": "u2"},
    )
    assert trans.status_code == 200
    if lifecycle_state == "effective":
        trans = client.post(
            f"/api/v1/objects/{policy_uuid}/transitions",
            json={"new_state": "effective", "actor_user_id": "u1"},
        )
        assert trans.status_code == 200
    return policy_uuid


def _create_risk_analysis(client, owner="u1"):
    """Create a risk analysis via API."""
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInitialEvaluationAPI:
    """Tests for POST/GET initial-risk-evaluations via API."""

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
        p = data["payload"]
        assert p["calculated_risk_level"] == "high"
        assert p["acceptable"] is False
        assert p["action_required"] == "control_required"
        assert p["risk_analysis_version"] == 1
        assert p["risk_policy_version"] == 1

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
        obj_uuid = create_resp.json()["object_uuid"]

        get_resp = client.get(f"/api/v1/initial-risk-evaluations/{obj_uuid}/versions/1")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["object_uuid"] == obj_uuid
        assert data["payload"]["calculated_risk_level"] == "high"

    def test_get_nonexistent_initial_evaluation(self, client):
        resp = client.get(
            f"/api/v1/initial-risk-evaluations/{uuid.uuid4().hex}/versions/1"
        )
        assert resp.status_code == 404

    def test_create_initial_missing_policy_returns_404(self, client):
        ra_uuid = _create_risk_analysis(client)
        fake_uuid = uuid.uuid4().hex

        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/initial-evaluations",
            json={
                "risk_analysis_version": 1,
                "risk_policy_uuid": fake_uuid,
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
                "severity": "nonexistent",  # will fail validation
                "probability": "possible",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 422


class TestResidualEvaluationAPI:
    """Tests for POST/GET residual-risk-evaluations via API."""

    def _create_initial_evaluation(self, client, ra_uuid, pol_uuid):
        """Helper to create an initial evaluation and return it."""
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
        assert resp.status_code == 201
        data = resp.json()
        assert data["object_version"] == 1
        assert data["lifecycle_state"] == "draft"
        p = data["payload"]
        assert p["calculated_risk_level"] == "medium"
        assert p["acceptable"] is True
        assert p["severity_improved"] is True
        assert p["probability_improved"] is True
        assert p["reduced"] is True
        assert p["regression_detected"] is False

    def test_get_residual_evaluation(self, client):
        ra_uuid = _create_risk_analysis(client)
        pol_uuid = _create_policy(client)
        ie = self._create_initial_evaluation(client, ra_uuid, pol_uuid)

        create_resp = client.post(
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
        assert create_resp.status_code == 201
        obj_uuid = create_resp.json()["object_uuid"]

        get_resp = client.get(
            f"/api/v1/residual-risk-evaluations/{obj_uuid}/versions/1"
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["object_uuid"] == obj_uuid
        assert data["payload"]["calculated_risk_level"] == "medium"

    def test_get_nonexistent_residual_evaluation(self, client):
        resp = client.get(
            f"/api/v1/residual-risk-evaluations/{uuid.uuid4().hex}/versions/1"
        )
        assert resp.status_code == 404

    def test_create_residual_missing_initial_returns_404(self, client):
        ra_uuid = _create_risk_analysis(client)
        _create_policy(client)  # policy exists but initial eval doesn't

        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/residual-evaluations",
            json={
                "risk_analysis_version": 1,
                "initial_evaluation_uuid": uuid.uuid4().hex,
                "initial_evaluation_version": 1,
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
                "residual_severity": "nonexistent",
                "residual_probability": "unlikely",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 422

    def test_residual_regression_detected(self, client):
        """Residual worse than initial = regression."""
        ra_uuid = _create_risk_analysis(client)
        pol_uuid = _create_policy(client)
        ie = self._create_initial_evaluation(client, ra_uuid, pol_uuid)

        # Residual is worse: moderate/possible → critical/probable
        resp = client.post(
            f"/api/v1/risk-analyses/{ra_uuid}/residual-evaluations",
            json={
                "risk_analysis_version": 1,
                "initial_evaluation_uuid": ie["object_uuid"],
                "initial_evaluation_version": 1,
                "residual_severity": "critical",
                "residual_probability": "probable",
                "evaluator_user_id": "u1",
            },
        )
        assert resp.status_code == 201
        p = resp.json()["payload"]
        assert p["regression_detected"] is True
        assert p["severity_worsened"] is True
        assert p["probability_worsened"] is True
        assert p["reduced"] is False
        assert p["calculated_risk_level"] == "intolerable"

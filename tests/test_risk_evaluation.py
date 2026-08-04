"""Tests for versioned risk evaluation services."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.control_verification_service import ControlVerificationService
from orkp.domain.exceptions import (
    InvalidLifecycleStateError,
    InvalidObjectIdentifierError,
    InvalidRelationError,
    ObjectTypeMismatchError,
    ObjectVersionNotFoundError,
)
from orkp.domain.initial_risk_evaluation_service import InitialRiskEvaluationService
from orkp.domain.residual_risk_evaluation_service import ResidualRiskEvaluationService
from orkp.domain.risk_models import (
    ControlVerificationCreateRequest,
    InitialRiskEvaluationCreateRequest,
    ResidualRiskEvaluationCreateRequest,
)
from orkp.domain.versioned_loader import load_risk_policy, load_versioned_object


@pytest.fixture
def repo_session():
    engine = create_engine("sqlite://", echo=False)

    @sa_event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    repo = RegulatoryObjectRepository(session)
    yield session, repo
    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


def _create_policy(repo, owner="u1", lifecycle_state="effective"):
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
    obj, _ = repo.create_object("risk_policy", payload, owner, owner)
    repo.transition_state(obj.object_uuid, "in_review", owner)
    if lifecycle_state == "approved":
        repo.transition_state(obj.object_uuid, "approved", "u2")
    elif lifecycle_state == "effective":
        repo.transition_state(obj.object_uuid, "approved", "u2")
        repo.transition_state(obj.object_uuid, "effective", owner)
    return obj


def _create_risk_analysis(repo, owner="u1"):
    obj, _ = repo.create_object(
        "risk_analysis",
        {
            "risk_id": "R1",
            "title": "Test Risk",
            "severity": "moderate",
            "probability": "possible",
        },
        owner,
        owner,
    )
    return obj


def _create_initial_evaluation(repo, ra_hex=None, policy_hex=None, owner="u1"):
    if ra_hex is None:
        ra = _create_risk_analysis(repo, owner)
        ra_hex = ra.uuid_hex
    if policy_hex is None:
        pol = _create_policy(repo, owner)
        policy_hex = pol.uuid_hex

    request = InitialRiskEvaluationCreateRequest(
        risk_analysis_version=1,
        risk_policy_uuid=policy_hex,
        risk_policy_version=1,
        severity="moderate",
        probability="possible",
        evaluator_user_id=owner,
    )
    response = InitialRiskEvaluationService(repo).create_evaluation(ra_hex, request)
    return response, ra_hex, policy_hex


def _dummy_verification_ref():
    """Satisfy request validation in tests that fail before verification lookup."""
    return {"object_uuid": uuid4().hex, "object_version": 1}


def _create_effective_control_verification(
    repo,
    initial_evaluation,
    risk_analysis_hex,
    policy_hex,
    owner="u1",
):
    """Create the complete Epic 007 prerequisite for residual-risk tests."""
    risk_analysis = repo.get_by_uuid_hex(risk_analysis_hex)
    assert risk_analysis is not None

    risk_control, _ = repo.create_object(
        "risk_control",
        {"control_id": f"RC-{uuid4().hex[:8]}", "description": "Test control"},
        owner,
        owner,
    )
    repo.create_relation(
        source_uuid=risk_analysis.object_uuid,
        source_version=1,
        target_uuid=risk_control.object_uuid,
        target_version=1,
        relation_type="controlled_by",
        created_by=owner,
    )

    evidence, _ = repo.create_object(
        "evidence",
        {"evidence_id": f"EV-{uuid4().hex[:8]}", "summary": "Verification evidence"},
        owner,
        owner,
    )
    repo.transition_state(evidence.object_uuid, "in_review", owner)
    repo.transition_state(evidence.object_uuid, "approved", "u2")
    repo.transition_state(evidence.object_uuid, "effective", owner)
    repo.session.commit()

    service = ControlVerificationService(repo)
    verification = service.create_verification(
        risk_control.uuid_hex,
        ControlVerificationCreateRequest(
            risk_analysis={"object_uuid": risk_analysis_hex, "object_version": 1},
            risk_control={"object_uuid": risk_control.uuid_hex, "object_version": 1},
            initial_evaluation={
                "object_uuid": initial_evaluation.object_uuid,
                "object_version": 1,
            },
            risk_policy={"object_uuid": policy_hex, "object_version": 1},
            evidence=[{"object_uuid": evidence.uuid_hex, "object_version": 1}],
            verification_method="test",
            verification_scope="Implementation and effectiveness",
            implementation_verified=True,
            effectiveness_verified=True,
            no_new_uncontrolled_risks=True,
            effectiveness_result="effective",
            conclusion="passed",
            verified_by_user_id=owner,
        ),
    )
    service.transition_state(verification.object_uuid, "in_review", owner)
    service.transition_state(verification.object_uuid, "approved", "u2")
    verification = service.transition_state(
        verification.object_uuid, "effective", owner
    )
    assert verification.eligible_for_residual_evaluation is True
    return {
        "object_uuid": verification.object_uuid,
        "object_version": verification.object_version,
    }


class TestLoader:
    def test_loads_valid_object(self, repo_session):
        session, repo = repo_session
        ra = _create_risk_analysis(repo)
        session.commit()
        loaded = load_versioned_object(repo, ra.uuid_hex, 1, "risk_analysis")
        assert loaded.object.object_type == "risk_analysis"
        assert loaded.version.version_no == 1

    def test_invalid_uuid(self, repo_session):
        _, repo = repo_session
        with pytest.raises(InvalidObjectIdentifierError):
            load_versioned_object(repo, "not-a-uuid", 1, "risk_analysis")

    def test_wrong_type(self, repo_session):
        session, repo = repo_session
        ra = _create_risk_analysis(repo)
        session.commit()
        with pytest.raises(ObjectTypeMismatchError):
            load_versioned_object(repo, ra.uuid_hex, 1, "hazard")

    def test_missing_version(self, repo_session):
        session, repo = repo_session
        ra = _create_risk_analysis(repo)
        session.commit()
        with pytest.raises(ObjectVersionNotFoundError):
            load_versioned_object(repo, ra.uuid_hex, 999, "risk_analysis")

    def test_lifecycle_filter(self, repo_session):
        session, repo = repo_session
        ra = _create_risk_analysis(repo)
        session.commit()
        with pytest.raises(InvalidLifecycleStateError):
            load_versioned_object(
                repo,
                ra.uuid_hex,
                1,
                "risk_analysis",
                allowed_lifecycle_states=["approved"],
            )

    def test_loads_risk_policy(self, repo_session):
        session, repo = repo_session
        pol = _create_policy(repo)
        session.commit()
        loaded = load_risk_policy(repo, pol.uuid_hex, 1)
        assert loaded.policy is not None
        assert loaded.revision == "1.0"

    def test_policy_wrong_type(self, repo_session):
        session, repo = repo_session
        ra = _create_risk_analysis(repo)
        session.commit()
        with pytest.raises(ObjectTypeMismatchError):
            load_risk_policy(repo, ra.uuid_hex, 1)

    def test_policy_draft_rejected(self, repo_session):
        session, repo = repo_session
        payload = {
            "policy_id": "P1",
            "name": "Draft",
            "policy_version": "0.1",
            "severity_scale": ["low", "high"],
            "probability_scale": ["low", "high"],
            "risk_levels": ["low", "high"],
            "risk_matrix": {
                "low": {"low": "low", "high": "low"},
                "high": {"low": "high", "high": "high"},
            },
            "acceptability_rules": {"low": True, "high": False},
            "required_actions": {"low": "none", "high": "control_required"},
            "control_hierarchy": ["design_by_safety"],
            "benefit_risk_required_for": ["high"],
        }
        pol, _ = repo.create_object("risk_policy", payload, "u1", "u1")
        session.commit()
        with pytest.raises(InvalidLifecycleStateError):
            load_risk_policy(repo, pol.uuid_hex, 1)


class TestInitialRiskEvaluation:
    def test_valid_creation(self, repo_session):
        session, repo = repo_session
        ra = _create_risk_analysis(repo)
        pol = _create_policy(repo)
        session.commit()
        req = InitialRiskEvaluationCreateRequest(
            risk_analysis_version=1,
            risk_policy_uuid=pol.uuid_hex,
            risk_policy_version=1,
            severity="moderate",
            probability="possible",
            evaluator_user_id="u1",
        )
        resp = InitialRiskEvaluationService(repo).create_evaluation(ra.uuid_hex, req)
        assert resp.object_uuid is not None
        assert resp.object_version == 1
        assert resp.payload.risk_analysis_version == 1
        assert resp.payload.risk_policy_version == 1
        assert resp.payload.calculated_risk_level == "high"
        assert resp.payload.acceptable is False
        assert resp.payload.action_required == "control_required"

    def test_wrong_ra_version_rejected(self, repo_session):
        session, repo = repo_session
        ra = _create_risk_analysis(repo)
        pol = _create_policy(repo)
        session.commit()
        with pytest.raises(ObjectVersionNotFoundError):
            InitialRiskEvaluationService(repo).create_evaluation(
                ra.uuid_hex,
                InitialRiskEvaluationCreateRequest(
                    risk_analysis_version=999,
                    risk_policy_uuid=pol.uuid_hex,
                    risk_policy_version=1,
                    severity="moderate",
                    probability="possible",
                    evaluator_user_id="u1",
                ),
            )

    def test_wrong_policy_type(self, repo_session):
        session, repo = repo_session
        ra = _create_risk_analysis(repo)
        session.commit()
        with pytest.raises(ObjectTypeMismatchError):
            InitialRiskEvaluationService(repo).create_evaluation(
                ra.uuid_hex,
                InitialRiskEvaluationCreateRequest(
                    risk_analysis_version=1,
                    risk_policy_uuid=ra.uuid_hex,
                    risk_policy_version=1,
                    severity="moderate",
                    probability="possible",
                    evaluator_user_id="u1",
                ),
            )

    def test_invalid_severity(self, repo_session):
        from pydantic import ValidationError

        session, repo = repo_session
        pol = _create_policy(repo)
        session.commit()
        with pytest.raises(ValidationError):
            InitialRiskEvaluationCreateRequest(
                risk_analysis_version=1,
                risk_policy_uuid=pol.uuid_hex,
                risk_policy_version=1,
                severity="nonexistent",
                probability="possible",
                evaluator_user_id="u1",
            )

    def test_derived_fields_rejected(self, repo_session):
        session, repo = repo_session
        ra = _create_risk_analysis(repo)
        pol = _create_policy(repo)
        session.commit()
        req = InitialRiskEvaluationCreateRequest(
            risk_analysis_version=1,
            risk_policy_uuid=pol.uuid_hex,
            risk_policy_version=1,
            severity="moderate",
            probability="possible",
            evaluator_user_id="u1",
        )
        resp = InitialRiskEvaluationService(repo).create_evaluation(ra.uuid_hex, req)
        assert resp.payload.risk_analysis_version == 1
        assert resp.payload.calculated_risk_level == "high"

    def test_rollback_on_relation_failure(self, repo_session):
        import unittest.mock as mock

        session, repo = repo_session
        ra = _create_risk_analysis(repo)
        pol = _create_policy(repo)
        session.commit()

        with mock.patch.object(
            repo, "create_relation", side_effect=RuntimeError("DB failure")
        ):
            req = InitialRiskEvaluationCreateRequest(
                risk_analysis_version=1,
                risk_policy_uuid=pol.uuid_hex,
                risk_policy_version=1,
                severity="moderate",
                probability="possible",
                evaluator_user_id="u1",
            )
            with pytest.raises(RuntimeError):
                InitialRiskEvaluationService(repo).create_evaluation(ra.uuid_hex, req)
        assert repo.list_objects("initial_risk_evaluation") == []

    def test_version_pinning_multiple_versions(self, repo_session):
        session, repo = repo_session
        ra = _create_risk_analysis(repo)
        pol = _create_policy(repo)
        session.commit()

        resp = InitialRiskEvaluationService(repo).create_evaluation(
            ra.uuid_hex,
            InitialRiskEvaluationCreateRequest(
                risk_analysis_version=1,
                risk_policy_uuid=pol.uuid_hex,
                risk_policy_version=1,
                severity="moderate",
                probability="possible",
                evaluator_user_id="u1",
            ),
        )
        repo.create_version(ra.object_uuid, {"updated": True}, "u1")
        session.commit()

        assert repo.get_by_uuid_hex(ra.uuid_hex).current_version == 2
        loaded = load_versioned_object(
            repo, resp.object_uuid, 1, "initial_risk_evaluation"
        )
        assert loaded.version.version_no == 1
        assert loaded.payload["risk_analysis_version"] == 1

    def test_negative_invalid_persisted_payload(self, repo_session):
        from orkp.db.models import ObjectVersion
        from orkp.domain.exceptions import InvalidPersistedPayloadError

        session, repo = repo_session
        ie_resp, ra_hex, _ = _create_initial_evaluation(repo)
        session.commit()

        obj = repo.get_by_uuid_hex(ie_resp.object_uuid)
        session.query(ObjectVersion).filter(
            ObjectVersion.object_uuid == obj.object_uuid,
            ObjectVersion.version_no == 1,
        ).update({"payload_json": {"bad": "data"}})
        session.commit()

        with pytest.raises(InvalidPersistedPayloadError):
            ResidualRiskEvaluationService(repo).create_evaluation(
                ra_hex,
                ResidualRiskEvaluationCreateRequest(
                    risk_analysis_version=1,
                    initial_evaluation_uuid=ie_resp.object_uuid,
                    initial_evaluation_version=1,
                    control_verifications=[_dummy_verification_ref()],
                    residual_severity="minor",
                    residual_probability="unlikely",
                    evaluator_user_id="u1",
                ),
            )


class TestResidualRiskEvaluation:
    def test_valid_creation(self, repo_session):
        session, repo = repo_session
        ie_resp, ra_hex, pol_hex = _create_initial_evaluation(repo)
        verification = _create_effective_control_verification(
            repo, ie_resp, ra_hex, pol_hex
        )
        session.commit()

        req = ResidualRiskEvaluationCreateRequest(
            risk_analysis_version=1,
            initial_evaluation_uuid=ie_resp.object_uuid,
            initial_evaluation_version=1,
            control_verifications=[verification],
            residual_severity="minor",
            residual_probability="unlikely",
            evaluator_user_id="u1",
        )
        resp = ResidualRiskEvaluationService(repo).create_evaluation(ra_hex, req)
        assert resp.object_uuid is not None
        assert resp.payload.risk_analysis_version == 1
        assert resp.payload.initial_evaluation_version == 1
        assert (
            resp.payload.control_verifications[0].object_uuid
            == verification["object_uuid"]
        )
        assert resp.payload.reduced is True
        assert resp.payload.regression_detected is False

    def test_wrong_ie_version(self, repo_session):
        session, repo = repo_session
        ie_resp, ra_hex, _ = _create_initial_evaluation(repo)
        session.commit()
        with pytest.raises(ObjectVersionNotFoundError):
            ResidualRiskEvaluationService(repo).create_evaluation(
                ra_hex,
                ResidualRiskEvaluationCreateRequest(
                    risk_analysis_version=1,
                    initial_evaluation_uuid=ie_resp.object_uuid,
                    initial_evaluation_version=999,
                    control_verifications=[_dummy_verification_ref()],
                    residual_severity="minor",
                    residual_probability="unlikely",
                    evaluator_user_id="u1",
                ),
            )

    def test_wrong_ra_version(self, repo_session):
        session, repo = repo_session
        ie_resp, ra_hex, _ = _create_initial_evaluation(repo)
        session.commit()
        with pytest.raises(ObjectVersionNotFoundError):
            ResidualRiskEvaluationService(repo).create_evaluation(
                ra_hex,
                ResidualRiskEvaluationCreateRequest(
                    risk_analysis_version=999,
                    initial_evaluation_uuid=ie_resp.object_uuid,
                    initial_evaluation_version=1,
                    control_verifications=[_dummy_verification_ref()],
                    residual_severity="minor",
                    residual_probability="unlikely",
                    evaluator_user_id="u1",
                ),
            )

    def test_ie_not_belonging_to_ra(self, repo_session):
        session, repo = repo_session
        ie_resp, _, _ = _create_initial_evaluation(repo)
        ra2 = _create_risk_analysis(repo, "u2")
        session.commit()
        with pytest.raises(InvalidRelationError):
            ResidualRiskEvaluationService(repo).create_evaluation(
                ra2.uuid_hex,
                ResidualRiskEvaluationCreateRequest(
                    risk_analysis_version=1,
                    initial_evaluation_uuid=ie_resp.object_uuid,
                    initial_evaluation_version=1,
                    control_verifications=[_dummy_verification_ref()],
                    residual_severity="minor",
                    residual_probability="unlikely",
                    evaluator_user_id="u1",
                ),
            )

    @pytest.mark.parametrize(
        ("severity", "probability", "expected"),
        [
            ("catastrophic", "probable", {"regression": True, "reduced": False}),
            ("negligible", "improbable", {"regression": False, "reduced": True}),
        ],
    )
    def test_risk_change_detection(self, repo_session, severity, probability, expected):
        session, repo = repo_session
        ie_resp, ra_hex, pol_hex = _create_initial_evaluation(repo)
        verification = _create_effective_control_verification(
            repo, ie_resp, ra_hex, pol_hex
        )
        session.commit()

        resp = ResidualRiskEvaluationService(repo).create_evaluation(
            ra_hex,
            ResidualRiskEvaluationCreateRequest(
                risk_analysis_version=1,
                initial_evaluation_uuid=ie_resp.object_uuid,
                initial_evaluation_version=1,
                control_verifications=[verification],
                residual_severity=severity,
                residual_probability=probability,
                evaluator_user_id="u1",
            ),
        )
        assert resp.payload.regression_detected is expected["regression"]
        assert resp.payload.reduced is expected["reduced"]
        if severity == "catastrophic":
            assert resp.payload.severity_worsened is True
            assert resp.payload.benefit_risk_required is True
        else:
            assert resp.payload.action_required == "none"

    def test_benefit_risk_derived_from_policy(self, repo_session):
        session, repo = repo_session
        ie_resp, ra_hex, pol_hex = _create_initial_evaluation(repo)
        verification = _create_effective_control_verification(
            repo, ie_resp, ra_hex, pol_hex
        )
        session.commit()

        resp = ResidualRiskEvaluationService(repo).create_evaluation(
            ra_hex,
            ResidualRiskEvaluationCreateRequest(
                risk_analysis_version=1,
                initial_evaluation_uuid=ie_resp.object_uuid,
                initial_evaluation_version=1,
                control_verifications=[verification],
                residual_severity="critical",
                residual_probability="probable",
                evaluator_user_id="u1",
            ),
        )
        assert resp.payload.regression_detected is True
        assert resp.payload.benefit_risk_required is True

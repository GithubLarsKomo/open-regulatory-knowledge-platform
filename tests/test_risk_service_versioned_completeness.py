"""Regression tests for version-pinned RiskService completeness gates."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.risk_service import RiskService


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _risk(repo):
    risk, _ = repo.create_object(
        "risk_analysis",
        {"risk_id": "R-COMP", "title": "Completeness risk"},
        "owner",
        "owner",
    )
    return risk


def _residual_payload(risk, *, acceptable, benefit_risk_required):
    return {
        "evaluation_id": f"rre-{uuid4().hex[:8]}",
        "risk_analysis_uuid": risk.uuid_hex,
        "risk_analysis_version": risk.current_version,
        "initial_evaluation_uuid": uuid4().hex,
        "initial_evaluation_version": 1,
        "control_verifications": [{"object_uuid": uuid4().hex, "object_version": 1}],
        "residual_severity": "critical",
        "residual_probability": "possible",
        "calculated_risk_level": "high",
        "acceptable": acceptable,
        "action_required": "none" if acceptable else "benefit_risk_required",
        "severity_improved": False,
        "probability_improved": True,
        "severity_worsened": False,
        "probability_worsened": False,
        "risk_level_improved": True,
        "reduced": True,
        "regression_detected": False,
        "benefit_risk_required": benefit_risk_required,
        "risk_policy_uuid": uuid4().hex,
        "risk_policy_version": 1,
        "policy_revision": "1.0",
        "evaluator_user_id": "owner",
        "rationale": "Residual risk assessment.",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def _add_residual(repo, risk, *, acceptable, benefit_risk_required):
    residual, _ = repo.create_object(
        "residual_risk_evaluation",
        _residual_payload(
            risk,
            acceptable=acceptable,
            benefit_risk_required=benefit_risk_required,
        ),
        "owner",
        "owner",
    )
    repo.create_relation(
        source_uuid=residual.object_uuid,
        source_version=1,
        target_uuid=risk.object_uuid,
        target_version=risk.current_version,
        relation_type="residual_of",
        created_by="owner",
    )
    repo.session.commit()
    return residual


def test_modern_acceptable_residual_is_recognized(repo):
    risk = _risk(repo)
    _add_residual(
        repo,
        risk,
        acceptable=True,
        benefit_risk_required=False,
    )

    result = RiskService(repo).evaluate_risk_completeness(risk.uuid_hex)

    assert not any(
        "RISK-EVAL-RESIDUAL-MISSING-001" in issue for issue in result["blocking_issues"]
    )
    assert not any("RISK-BENEFIT-001" in issue for issue in result["blocking_issues"])


def test_unacceptable_residual_has_exactly_one_benefit_risk_blocker(repo):
    risk = _risk(repo)
    _add_residual(
        repo,
        risk,
        acceptable=False,
        benefit_risk_required=True,
    )

    result = RiskService(repo).evaluate_risk_completeness(risk.uuid_hex)

    benefit_issues = [
        issue for issue in result["blocking_issues"] if "RISK-BENEFIT-001" in issue
    ]
    assert len(benefit_issues) == 1


def test_approved_favorable_benefit_risk_clears_residual_blocker(repo):
    risk = _risk(repo)
    residual = _add_residual(
        repo,
        risk,
        acceptable=False,
        benefit_risk_required=True,
    )
    residual_version = repo.get_version(residual.object_uuid, 1)
    residual_payload = residual_version.payload_json

    analysis, _ = repo.create_object(
        "benefit_risk",
        {
            "residual_evaluation": {
                "object_uuid": residual.uuid_hex,
                "object_version": 1,
            },
            "risk_analysis": {
                "object_uuid": risk.uuid_hex,
                "object_version": 1,
            },
            "risk_policy": {
                "object_uuid": residual_payload["risk_policy_uuid"],
                "object_version": residual_payload["risk_policy_version"],
            },
            "benefits": "Clinical benefit outweighs residual risk.",
            "residual_risks": "High residual risk remains.",
            "rationale": "The benefit is clinically meaningful.",
            "conclusion": "favorable",
            "evaluator_user_id": "reviewer",
            "analysis_id": "bra-test",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        },
        "reviewer",
        "reviewer",
    )
    repo.create_relation(
        source_uuid=analysis.object_uuid,
        source_version=1,
        target_uuid=residual.object_uuid,
        target_version=1,
        relation_type="benefit_risk_for",
        created_by="reviewer",
    )
    repo.transition_state(analysis.object_uuid, "in_review", "reviewer")
    repo.transition_state(analysis.object_uuid, "approved", "approver")
    repo.session.commit()

    result = RiskService(repo).evaluate_risk_completeness(risk.uuid_hex)

    assert not any("RISK-BENEFIT-001" in issue for issue in result["blocking_issues"])
    assert any("RISK-BENEFIT-001" in warning for warning in result["warnings"])


def test_historical_residual_relation_does_not_satisfy_current_risk_version(repo):
    risk = _risk(repo)
    _add_residual(
        repo,
        risk,
        acceptable=True,
        benefit_risk_required=False,
    )
    repo.create_version(
        risk.object_uuid,
        {"risk_id": "R-COMP", "title": "Completeness risk v2"},
        "owner",
    )
    repo.session.commit()

    result = RiskService(repo).evaluate_risk_completeness(risk.uuid_hex)

    assert any(
        "RISK-EVAL-RESIDUAL-MISSING-001" in issue for issue in result["blocking_issues"]
    )


def _control_verification_payload(risk, control):
    return {
        "risk_analysis": {
            "object_uuid": risk.uuid_hex,
            "object_version": risk.current_version,
        },
        "risk_control": {
            "object_uuid": control.uuid_hex,
            "object_version": control.current_version,
        },
        "initial_evaluation": {
            "object_uuid": uuid4().hex,
            "object_version": 1,
        },
        "risk_policy": {"object_uuid": uuid4().hex, "object_version": 1},
        "evidence": [{"object_uuid": uuid4().hex, "object_version": 1}],
        "verification_method": "test",
        "verification_scope": "Implementation and effectiveness",
        "implementation_verified": True,
        "effectiveness_verified": True,
        "no_new_uncontrolled_risks": True,
        "effectiveness_result": "effective",
        "conclusion": "passed",
        "verified_by_user_id": "verifier",
        "verification_id": "cv-test",
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def test_control_counts_as_verified_only_after_verification_is_effective(repo):
    risk = _risk(repo)
    control, _ = repo.create_object(
        "risk_control",
        {"control_id": "RC-1", "verification_required": True},
        "owner",
        "owner",
    )
    repo.create_relation(
        source_uuid=risk.object_uuid,
        source_version=1,
        target_uuid=control.object_uuid,
        target_version=1,
        relation_type="controlled_by",
        created_by="owner",
    )
    verification, _ = repo.create_object(
        "control_verification",
        _control_verification_payload(risk, control),
        "verifier",
        "verifier",
    )
    repo.create_relation(
        source_uuid=verification.object_uuid,
        source_version=1,
        target_uuid=control.object_uuid,
        target_version=1,
        relation_type="verifies_control",
        created_by="verifier",
    )
    repo.session.commit()

    draft_result = RiskService(repo).evaluate_risk_completeness(risk.uuid_hex)
    assert any(
        "RISK-CONTROL-VERIFICATION-MISSING-001" in issue
        for issue in draft_result["blocking_issues"]
    )

    repo.transition_state(verification.object_uuid, "in_review", "verifier")
    repo.transition_state(verification.object_uuid, "approved", "approver")
    repo.transition_state(verification.object_uuid, "effective", "verifier")
    repo.session.commit()

    effective_result = RiskService(repo).evaluate_risk_completeness(risk.uuid_hex)
    assert not any(
        "RISK-CONTROL-VERIFICATION-MISSING-001" in issue
        for issue in effective_result["blocking_issues"]
    )

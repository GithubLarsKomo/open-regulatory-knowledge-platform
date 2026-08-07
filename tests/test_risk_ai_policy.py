"""Regression tests for the Risk-domain AI draft-only boundary."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from orkp.domain.exceptions import AuthorizationError, RiskEvaluationError
from orkp.domain.risk_ai_policy import (
    RISK_AI_ALLOWED_DRAFT_FIELDS,
    RISK_AI_FORBIDDEN_DECISION_FIELDS,
    validate_ai_risk_draft,
)
from orkp.domain.risk_models import (
    InitialRiskEvaluationCreateRequest,
    ResidualRiskEvaluationCreateRequest,
)


def test_ai_risk_draft_accepts_supporting_text_only():
    draft = validate_ai_risk_draft(
        {
            "rationale": "  Explain the clinical rationale.  ",
            "assumptions": "Assumption text",
            "review_checklist": [" Check traceability ", "", "Review uncertainty"],
        }
    )

    assert draft.rationale == "Explain the clinical rationale."
    assert draft.assumptions == "Assumption text"
    assert draft.review_checklist == ["Check traceability", "Review uncertainty"]
    assert RISK_AI_ALLOWED_DRAFT_FIELDS.isdisjoint(RISK_AI_FORBIDDEN_DECISION_FIELDS)


def test_ai_risk_draft_rejects_acceptability_and_benefit_risk_decisions():
    for field, value in {
        "acceptable": True,
        "acceptability": "acceptable",
        "overall_acceptable": True,
        "conclusion": "favorable",
        "benefit_risk_required": False,
        "action_required": "none",
    }.items():
        with pytest.raises(AuthorizationError, match=field):
            validate_ai_risk_draft({"rationale": "Draft", field: value})


def test_ai_risk_draft_rejects_risk_estimate_inputs_and_outputs():
    for field in (
        "severity",
        "probability",
        "risk_level",
        "calculated_risk_level",
        "residual_severity",
        "residual_probability",
        "residual_acceptable",
    ):
        with pytest.raises(AuthorizationError, match=field):
            validate_ai_risk_draft({"rationale": "Draft", field: "critical"})


def test_ai_risk_draft_rejects_verification_and_lifecycle_decisions():
    for field, value in {
        "implementation_verified": True,
        "effectiveness_verified": True,
        "no_new_uncontrolled_risks": True,
        "effectiveness_result": "effective",
        "verification_conclusion": "passed",
        "lifecycle_state": "approved",
        "approval_decision": "approved",
        "approved": True,
        "new_state": "approved",
    }.items():
        with pytest.raises(AuthorizationError, match=field):
            validate_ai_risk_draft({"rationale": "Draft", field: value})


def test_ai_risk_draft_rejects_unknown_or_empty_content():
    with pytest.raises(RiskEvaluationError, match="unsupported fields"):
        validate_ai_risk_draft({"rationale": "Draft", "custom_score": 7})

    with pytest.raises(RiskEvaluationError, match="content is invalid"):
        validate_ai_risk_draft({"rationale": "   ", "review_checklist": []})


def test_initial_and_residual_requests_cannot_set_acceptable_directly():
    policy_uuid = uuid4().hex
    with pytest.raises(ValidationError):
        InitialRiskEvaluationCreateRequest(
            risk_analysis_version=1,
            risk_policy_uuid=policy_uuid,
            risk_policy_version=1,
            severity="moderate",
            probability="possible",
            evaluator_user_id="human-evaluator",
            acceptable=True,
        )

    with pytest.raises(ValidationError):
        ResidualRiskEvaluationCreateRequest(
            risk_analysis_version=1,
            initial_evaluation_uuid=uuid4().hex,
            initial_evaluation_version=1,
            control_verifications=[
                {"object_uuid": uuid4().hex, "object_version": 1}
            ],
            residual_severity="moderate",
            residual_probability="possible",
            evaluator_user_id="human-evaluator",
            acceptable=True,
        )

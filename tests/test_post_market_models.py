"""Strict-model regression tests for Risk Impact Assessment payloads."""

import pytest
from pydantic import ValidationError

from orkp.domain.post_market_models import RiskImpactAssessmentDraftPayload


def _base_payload():
    return {
        "assessment_id": "ria-model-test",
        "risk_analysis": {"object_uuid": "0" * 32, "object_version": 1},
        "post_market_information": {"object_uuid": "1" * 32, "object_version": 1},
    }


def test_pending_assessment_cannot_claim_no_review_required():
    with pytest.raises(ValidationError):
        RiskImpactAssessmentDraftPayload(
            **_base_payload(),
            outcome="pending",
            requires_risk_review=False,
        )


def test_completed_assessment_requires_human_decision_metadata():
    with pytest.raises(ValidationError):
        RiskImpactAssessmentDraftPayload(
            **_base_payload(),
            outcome="no_change",
            requires_risk_review=False,
        )


@pytest.mark.parametrize(
    ("outcome", "requires_risk_review"),
    [
        ("no_change", True),
        ("review_required", False),
        ("risk_increase", False),
        ("new_risk_identified", False),
        ("control_effectiveness_concern", False),
    ],
)
def test_completed_outcome_and_review_flag_must_be_consistent(
    outcome,
    requires_risk_review,
):
    with pytest.raises(ValidationError):
        RiskImpactAssessmentDraftPayload(
            **_base_payload(),
            outcome=outcome,
            rationale="Human impact rationale.",
            requires_risk_review=requires_risk_review,
            assessor_user_id="assessor",
            assessed_at="2026-08-05T12:00:00+00:00",
        )

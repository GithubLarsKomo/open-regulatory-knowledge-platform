"""AI drafting boundary for the Risk domain.

AI may propose supporting rationale text, but it must not write fields that
constitute or determine Risk acceptability, verification, or lifecycle decisions.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from orkp.domain.exceptions import AuthorizationError, RiskEvaluationError


RISK_AI_ALLOWED_DRAFT_FIELDS = frozenset(
    {
        "rationale",
        "assumptions",
        "uncertainty",
        "benefits",
        "residual_risks",
        "considerations",
        "notes",
        "review_checklist",
    }
)

RISK_AI_FORBIDDEN_DECISION_FIELDS = frozenset(
    {
        # Explicit acceptability / Benefit-Risk decisions.
        "acceptable",
        "acceptability",
        "overall_acceptable",
        "overall_acceptability",
        "conclusion",
        "benefit_risk_required",
        "action_required",
        # Inputs or outputs that determine policy-based acceptability.
        "severity",
        "probability",
        "risk_level",
        "calculated_risk_level",
        "residual_severity",
        "residual_probability",
        "residual_acceptable",
        # Control-verification decisions feeding residual-risk evaluation.
        "implementation_verified",
        "effectiveness_verified",
        "no_new_uncontrolled_risks",
        "effectiveness_result",
        "verification_conclusion",
        # Lifecycle / approval decisions.
        "lifecycle_state",
        "approval_decision",
        "approved",
        "new_state",
    }
)


class RiskAIDraftContent(BaseModel):
    """Non-decisional Risk text that an AI integration may propose."""

    model_config = ConfigDict(extra="forbid")

    rationale: str | None = None
    assumptions: str | None = None
    uncertainty: str | None = None
    benefits: str | None = None
    residual_risks: str | None = None
    considerations: str | None = None
    notes: str | None = None
    review_checklist: list[str] = Field(default_factory=list)

    @field_validator(
        "rationale",
        "assumptions",
        "uncertainty",
        "benefits",
        "residual_risks",
        "considerations",
        "notes",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("review_checklist")
    @classmethod
    def normalize_checklist(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        return normalized

    @model_validator(mode="after")
    def require_draft_content(self):
        text_values = (
            self.rationale,
            self.assumptions,
            self.uncertainty,
            self.benefits,
            self.residual_risks,
            self.considerations,
            self.notes,
        )
        if not any(text_values) and not self.review_checklist:
            raise ValueError("AI Risk draft must contain at least one support-text field")
        return self


def validate_ai_risk_draft(payload: Mapping[str, Any]) -> RiskAIDraftContent:
    """Validate AI-proposed Risk content without permitting decision fields."""

    forbidden = sorted(set(payload) & RISK_AI_FORBIDDEN_DECISION_FIELDS)
    if forbidden:
        raise AuthorizationError(
            "AI Risk drafting cannot set decision fields: " + ", ".join(forbidden)
        )

    unsupported = sorted(set(payload) - RISK_AI_ALLOWED_DRAFT_FIELDS)
    if unsupported:
        raise RiskEvaluationError(
            "AI Risk drafting contains unsupported fields: " + ", ".join(unsupported)
        )

    try:
        return RiskAIDraftContent(**dict(payload))
    except ValidationError as exc:
        raise RiskEvaluationError("AI Risk draft content is invalid") from exc

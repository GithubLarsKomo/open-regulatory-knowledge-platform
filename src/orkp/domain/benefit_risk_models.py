"""Strict models for version-pinned Benefit-Risk Analysis."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from orkp.domain.risk_models import BENEFIT_RISK_CONCLUSION, VersionedObjectReference


class BenefitRiskAnalysisCreateRequest(BaseModel):
    """Create a Benefit-Risk Analysis for an exact residual-risk context."""

    model_config = ConfigDict(extra="forbid")
    residual_evaluation: VersionedObjectReference
    risk_analysis: VersionedObjectReference
    risk_policy: VersionedObjectReference
    benefits: str = Field(..., min_length=1)
    residual_risks: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    conclusion: str
    evaluator_user_id: str = Field(..., min_length=1)

    @field_validator("benefits", "residual_risks", "rationale", "evaluator_user_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("conclusion")
    @classmethod
    def validate_conclusion(cls, value: str) -> str:
        if value not in BENEFIT_RISK_CONCLUSION:
            raise ValueError(f"Invalid benefit-risk conclusion '{value}'")
        return value


class BenefitRiskAnalysisPayload(BenefitRiskAnalysisCreateRequest):
    """Persisted Benefit-Risk Analysis payload."""

    analysis_id: str = Field(..., min_length=1)
    evaluated_at: str


class BenefitRiskAnalysisResponse(BaseModel):
    """Version-pinned Benefit-Risk Analysis object envelope."""

    model_config = ConfigDict(extra="forbid")
    object_uuid: str
    object_version: int
    lifecycle_state: str
    payload: BenefitRiskAnalysisPayload

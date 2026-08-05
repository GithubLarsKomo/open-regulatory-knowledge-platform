"""Strict models for version-pinned Benefit-Risk Analysis."""

from pydantic import BaseModel, ConfigDict, Field

from orkp.domain.risk_models import BenefitRiskPayload, VersionedObjectReference


class BenefitRiskAnalysisCreateRequest(BenefitRiskPayload):
    """Create a Benefit-Risk Analysis for an exact residual-risk context."""

    model_config = ConfigDict(extra="forbid")
    residual_evaluation: VersionedObjectReference
    risk_analysis: VersionedObjectReference
    risk_policy: VersionedObjectReference
    evaluator_user_id: str = Field(..., min_length=1)


class BenefitRiskAnalysisPayload(BenefitRiskAnalysisCreateRequest):
    """Persisted Benefit-Risk Analysis payload."""

    evaluated_at: str


class BenefitRiskAnalysisResponse(BaseModel):
    """Version-pinned Benefit-Risk Analysis object envelope."""

    model_config = ConfigDict(extra="forbid")
    object_uuid: str
    object_version: int
    lifecycle_state: str
    payload: BenefitRiskAnalysisPayload

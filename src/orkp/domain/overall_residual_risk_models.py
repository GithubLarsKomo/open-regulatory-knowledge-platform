"""Strict models for product-level Overall Residual Risk evaluation."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orkp.domain.risk_models import VersionedObjectReference


class OverallResidualRiskCreateRequest(BaseModel):
    """Human Overall Residual Risk judgment for an exact Product version."""

    model_config = ConfigDict(extra="forbid")
    product: VersionedObjectReference
    acceptable: bool
    rationale: str = Field(..., min_length=1)
    evaluator_user_id: str = Field(..., min_length=1)
    considerations: Optional[str] = None

    @field_validator("rationale", "evaluator_user_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("considerations")
    @classmethod
    def strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class OverallResidualRiskEntry(BaseModel):
    """Exact source disposition for one Product Risk Analysis."""

    model_config = ConfigDict(extra="forbid")
    risk_analysis: VersionedObjectReference
    residual_evaluation: VersionedObjectReference
    risk_policy: VersionedObjectReference
    residual_acceptable: bool
    benefit_risk_analyses: list[VersionedObjectReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_benefit_risk_references(self):
        keys = {
            (reference.object_uuid, reference.object_version)
            for reference in self.benefit_risk_analyses
        }
        if len(keys) != len(self.benefit_risk_analyses):
            raise ValueError("benefit_risk_analyses must not contain duplicates")
        return self


class OverallResidualRiskPayload(OverallResidualRiskCreateRequest):
    """Persisted Overall Residual Risk evaluation payload."""

    evaluation_id: str = Field(..., min_length=1)
    entries: list[OverallResidualRiskEntry] = Field(..., min_length=1)
    evaluated_at: str

    @model_validator(mode="after")
    def reject_duplicate_risk_entries(self):
        keys = {
            (entry.risk_analysis.object_uuid, entry.risk_analysis.object_version)
            for entry in self.entries
        }
        if len(keys) != len(self.entries):
            raise ValueError(
                "entries must not contain duplicate risk-analysis versions"
            )
        return self


class OverallResidualRiskResponse(BaseModel):
    """Version-pinned Overall Residual Risk object envelope."""

    model_config = ConfigDict(extra="forbid")
    object_uuid: str
    object_version: int
    lifecycle_state: str
    payload: OverallResidualRiskPayload

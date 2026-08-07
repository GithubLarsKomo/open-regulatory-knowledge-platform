"""Strict models for Performance Result evidence."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orkp.domain.risk_models import VersionedObjectReference


PERFORMANCE_RESULT_QUALITY = {"high", "medium", "low"}
PERFORMANCE_EVIDENCE_TYPES = {
    "analytical": "analytical_study",
    "clinical": "clinical_study",
    "scientific_validity": "scientific_validity",
}


class PerformanceResultCreateRequest(BaseModel):
    """Create one structured Performance Result for exact Study/Claim versions."""

    model_config = ConfigDict(extra="forbid")

    result_id: str = Field(..., min_length=1)
    study: VersionedObjectReference
    claims: list[VersionedObjectReference] = Field(..., min_length=1)
    parameter: str = Field(..., min_length=1)
    result_value: str = Field(..., min_length=1)
    unit: str | None = None
    statistical_method: str | None = None
    interpretation: str | None = None
    quality_rating: str = "medium"
    owner_user_id: str = Field(..., min_length=1)

    @field_validator("result_id", "parameter", "result_value", "owner_user_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("unit", "statistical_method", "interpretation")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("quality_rating")
    @classmethod
    def validate_quality_rating(cls, value: str) -> str:
        if value not in PERFORMANCE_RESULT_QUALITY:
            raise ValueError(f"Invalid quality_rating '{value}'")
        return value

    @model_validator(mode="after")
    def reject_duplicate_claims(self):
        keys = {
            (reference.object_uuid, reference.object_version)
            for reference in self.claims
        }
        if len(keys) != len(self.claims):
            raise ValueError("claims must not contain duplicates")
        return self


class PerformanceResultPayload(PerformanceResultCreateRequest):
    """Persisted Performance Result evidence payload."""

    evidence_type: str

    @field_validator("evidence_type")
    @classmethod
    def validate_evidence_type(cls, value: str) -> str:
        if value not in PERFORMANCE_EVIDENCE_TYPES.values():
            raise ValueError(f"Invalid Performance Result evidence_type '{value}'")
        return value


class PerformanceResultResponse(BaseModel):
    """Version-pinned Performance Result response envelope."""

    model_config = ConfigDict(extra="forbid")

    object_uuid: str
    object_version: int
    lifecycle_state: str
    payload: PerformanceResultPayload

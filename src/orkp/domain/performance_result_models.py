"""Strict models for Performance Result evidence."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orkp.domain.risk_models import VersionedObjectReference


PERFORMANCE_RESULT_QUALITY = {"high", "medium", "low"}
PERFORMANCE_EVIDENCE_TYPES = {
    "analytical": "analytical_study",
    "clinical": "clinical_study",
    "scientific_validity": "scientific_validity",
}
PERFORMANCE_STATISTICAL_SOURCE_KINDS = {"source_data", "validated_report"}


class PerformanceStatisticalSource(BaseModel):
    """Exact provenance source for a statistical Performance Result."""

    model_config = ConfigDict(extra="forbid")

    source_kind: str
    evidence: VersionedObjectReference

    @field_validator("source_kind")
    @classmethod
    def validate_source_kind(cls, value: str) -> str:
        if value not in PERFORMANCE_STATISTICAL_SOURCE_KINDS:
            raise ValueError(f"Invalid statistical source_kind '{value}'")
        return value


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
    statistical_sources: list[PerformanceStatisticalSource] = Field(default_factory=list)
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
    def validate_exact_reference_sets(self):
        claim_keys = {
            (reference.object_uuid, reference.object_version)
            for reference in self.claims
        }
        if len(claim_keys) != len(self.claims):
            raise ValueError("claims must not contain duplicates")

        source_keys = {
            (source.evidence.object_uuid, source.evidence.object_version)
            for source in self.statistical_sources
        }
        if len(source_keys) != len(self.statistical_sources):
            raise ValueError("statistical_sources must not contain duplicates")

        if self.statistical_method and not self.statistical_sources:
            raise ValueError(
                "statistical_sources are required when statistical_method is provided"
            )
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

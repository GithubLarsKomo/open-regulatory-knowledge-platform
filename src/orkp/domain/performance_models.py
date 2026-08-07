"""Strict models for the Performance domain."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from orkp.domain.risk_models import VersionedObjectReference


PERFORMANCE_STUDY_TYPES = {
    "analytical",
    "clinical",
    "scientific_validity",
}
PERFORMANCE_STUDY_STATUSES = {
    "planned",
    "ongoing",
    "completed",
    "archived",
}


class PerformanceStudyCreateRequest(BaseModel):
    """Create a structured Performance Study for an exact Product version."""

    model_config = ConfigDict(extra="forbid")

    study_id: str = Field(..., min_length=1)
    study_type: str
    title: str = Field(..., min_length=1)
    description: str | None = None
    product: VersionedObjectReference
    study_status: str = "planned"
    owner_user_id: str = Field(..., min_length=1)

    @field_validator("study_id", "title", "owner_user_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("description")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("study_type")
    @classmethod
    def validate_study_type(cls, value: str) -> str:
        if value not in PERFORMANCE_STUDY_TYPES:
            raise ValueError(f"Invalid study_type '{value}'")
        return value

    @field_validator("study_status")
    @classmethod
    def validate_study_status(cls, value: str) -> str:
        if value not in PERFORMANCE_STUDY_STATUSES:
            raise ValueError(f"Invalid study_status '{value}'")
        return value


class PerformanceStudyPayload(PerformanceStudyCreateRequest):
    """Persisted structured Performance Study payload."""


class PerformanceStudyResponse(BaseModel):
    """Version-pinned Performance Study response envelope."""

    model_config = ConfigDict(extra="forbid")

    object_uuid: str
    object_version: int
    lifecycle_state: str
    payload: PerformanceStudyPayload

"""Strict frozen completeness models for PER report baselines."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from orkp.domain.performance_gap_models import PerformanceClaimGapReport
from orkp.domain.risk_models import VersionedObjectReference


class PERCompletenessSnapshotPayload(BaseModel):
    """Persisted snapshot of the existing Performance Claim gap report."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "per-completeness-1.0"
    source_performance_baseline_uuid: str = Field(..., min_length=1)
    gap_report: PerformanceClaimGapReport
    owner_user_id: str = Field(..., min_length=1)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != "per-completeness-1.0":
            raise ValueError("Unsupported PER completeness schema_version")
        return value

    @field_validator("source_performance_baseline_uuid", "owner_user_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class PERCompletenessReport(BaseModel):
    """Completeness report exposed in a generated PER draft."""

    model_config = ConfigDict(extra="forbid")

    snapshot_ref: VersionedObjectReference
    gap_report: PerformanceClaimGapReport

"""Strict models for reproducible baseline-only PER draft manifests."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from orkp.domain.performance_report_models import (
    PerformanceReportPayload,
    PerformanceReportSnapshot,
)
from orkp.domain.risk_models import VersionedObjectReference


class PERTraceabilityEntry(BaseModel):
    """Exact frozen source references for one PER Performance Result."""

    model_config = ConfigDict(extra="forbid")

    section_type: str
    performance_result: VersionedObjectReference
    study: VersionedObjectReference
    claims: list[VersionedObjectReference]
    statistical_sources: list[VersionedObjectReference]


class PERDraftPayload(BaseModel):
    """Canonical JSON-first PER draft manifest."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "per-draft-1.0"
    baseline_uuid: str
    baseline_name: str
    baseline_description: str | None = None
    product: PerformanceReportSnapshot
    performance_sections: PerformanceReportPayload
    traceability_appendix: list[PERTraceabilityEntry]


class PERDraftGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_by_user_id: str = Field(..., min_length=1)

    @field_validator("generated_by_user_id")
    @classmethod
    def strip_generated_by(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class PERDraftGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_uuid: str
    baseline_uuid: str
    checksum_sha256: str
    canonical_json: str
    format: str = "json"
    draft: PERDraftPayload

"""Strict models for reproducible baseline-only PER draft manifests."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orkp.domain.per_completeness_models import PERCompletenessReport
from orkp.domain.per_content_models import PERContentBlock
from orkp.domain.per_section_coverage_models import PERSectionCoverageReport
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

    schema_version: str = "per-draft-1.1"
    baseline_uuid: str
    baseline_name: str
    baseline_description: str | None = None
    product: PerformanceReportSnapshot
    performance_sections: PerformanceReportPayload
    content_blocks: list[PERContentBlock]
    completeness_report: PERCompletenessReport | None = None
    section_coverage: PERSectionCoverageReport | None = None
    traceability_appendix: list[PERTraceabilityEntry]

    @model_validator(mode="after")
    def validate_schema_contract(self):
        if self.schema_version == "per-draft-1.1":
            if (
                self.completeness_report is not None
                or self.section_coverage is not None
            ):
                raise ValueError(
                    "per-draft-1.1 cannot contain report-level completeness or section coverage"
                )
            return self
        if self.schema_version == "per-draft-1.3":
            if self.completeness_report is None or self.section_coverage is None:
                raise ValueError(
                    "per-draft-1.3 requires completeness and canonical section coverage"
                )
            return self
        raise ValueError(
            f"Unsupported PER draft schema_version '{self.schema_version}'"
        )


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

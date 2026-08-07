"""Strict models for reproducible Performance Evaluation Report sections."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orkp.domain.risk_models import VersionedObjectReference


PER_SECTION_TYPES = {
    "scientific_validity",
    "analytical_performance",
    "clinical_performance",
}


class PerformanceReportBaselineCreateRequest(BaseModel):
    """Freeze exact approved Performance Evaluation inputs."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    description: str | None = None
    product: VersionedObjectReference
    evidence: list[VersionedObjectReference] = Field(..., min_length=1)
    created_by_user_id: str = Field(..., min_length=1)

    @field_validator("name", "created_by_user_id")
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

    @model_validator(mode="after")
    def reject_duplicate_evidence(self):
        keys = {
            (reference.object_uuid, reference.object_version)
            for reference in self.evidence
        }
        if len(keys) != len(self.evidence):
            raise ValueError("evidence must not contain duplicates")
        return self


class PerformanceReportBaselineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_uuid: str
    name: str
    description: str | None = None
    product: VersionedObjectReference
    evidence_count: int
    item_count: int
    created_by_user_id: str


class PerformanceReportSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_uuid: str
    object_type: str
    object_version: int
    snapshot: dict[str, Any]


class PerformanceReportSectionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    performance_result: PerformanceReportSnapshot
    study: PerformanceReportSnapshot
    claims: list[PerformanceReportSnapshot]
    statistical_sources: list[PerformanceReportSnapshot]


class PerformanceReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_type: str
    items: list[PerformanceReportSectionItem]

    @field_validator("section_type")
    @classmethod
    def validate_section_type(cls, value: str) -> str:
        if value not in PER_SECTION_TYPES:
            raise ValueError(f"Invalid PER section_type '{value}'")
        return value


class PerformanceReportPayload(BaseModel):
    """Canonical deterministic PER section representation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "per-sections-1.0"
    baseline_uuid: str
    baseline_name: str
    baseline_description: str | None = None
    product: PerformanceReportSnapshot
    sections: list[PerformanceReportSection]


class PerformanceReportGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_by_user_id: str = Field(..., min_length=1)

    @field_validator("generated_by_user_id")
    @classmethod
    def strip_generated_by(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class PerformanceReportGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_uuid: str
    baseline_uuid: str
    checksum_sha256: str
    canonical_json: str
    format: str = "json"
    report: PerformanceReportPayload

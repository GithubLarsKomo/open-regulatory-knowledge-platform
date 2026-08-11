"""Strict frozen coverage models for the canonical ten-section PER structure."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orkp.domain.risk_models import VersionedObjectReference


PER_CANONICAL_SECTION_IDS = (
    "cover_page",
    "intended_purpose",
    "scientific_validity",
    "analytical_performance",
    "clinical_performance",
    "claims_and_evidence",
    "risk_benefit_analysis",
    "pmpf_summary",
    "traceability_appendix",
    "completeness_report",
)

PER_SECTION_GAP_CODE_BY_ID = {
    "intended_purpose": "PER-SECTION-INTENDED-PURPOSE-MISSING",
    "scientific_validity": "PER-SECTION-SCIENTIFIC-VALIDITY-MISSING",
    "analytical_performance": "PER-SECTION-ANALYTICAL-PERFORMANCE-MISSING",
    "clinical_performance": "PER-SECTION-CLINICAL-PERFORMANCE-MISSING",
    "claims_and_evidence": "PER-SECTION-CLAIMS-EVIDENCE-MISSING",
    "risk_benefit_analysis": "PER-SECTION-RISK-BENEFIT-MISSING",
    "pmpf_summary": "PER-SECTION-PMPF-MISSING",
    "traceability_appendix": "PER-SECTION-TRACEABILITY-MISSING",
}
PER_SECTION_GAP_CODES = set(PER_SECTION_GAP_CODE_BY_ID.values())


class PERCanonicalSection(BaseModel):
    """One deterministic canonical PER section and its frozen source coverage."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    status: Literal["available", "missing"]
    source_refs: list[VersionedObjectReference] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    gap_code: str | None = None

    @field_validator("section_id")
    @classmethod
    def validate_section_id(cls, value: str) -> str:
        if value not in PER_CANONICAL_SECTION_IDS:
            raise ValueError(f"Invalid canonical PER section_id '{value}'")
        return value

    @field_validator("gap_code")
    @classmethod
    def validate_gap_code(cls, value: str | None) -> str | None:
        if value is not None and value not in PER_SECTION_GAP_CODES:
            raise ValueError(f"Invalid canonical PER section gap_code '{value}'")
        return value

    @model_validator(mode="after")
    def validate_status_contract(self):
        keys = [(ref.object_uuid, ref.object_version) for ref in self.source_refs]
        if len(keys) != len(set(keys)):
            raise ValueError("canonical PER section source_refs must be unique")

        if self.status == "available":
            if self.gap_code is not None:
                raise ValueError(
                    "available canonical PER section cannot carry gap_code"
                )
            if not self.source_refs:
                raise ValueError("available canonical PER section requires source_refs")
            return self

        expected_gap = PER_SECTION_GAP_CODE_BY_ID.get(self.section_id)
        if expected_gap is None:
            raise ValueError(
                f"Canonical PER section '{self.section_id}' cannot be marked missing"
            )
        if self.gap_code != expected_gap:
            raise ValueError(
                f"Missing canonical PER section '{self.section_id}' requires gap_code '{expected_gap}'"
            )
        return self


class PERSectionCoverageSnapshotPayload(BaseModel):
    """Persisted report-level snapshot of all ten canonical PER sections."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "per-section-coverage-1.0"
    source_performance_baseline_uuid: str = Field(..., min_length=1)
    sections: list[PERCanonicalSection]
    owner_user_id: str = Field(..., min_length=1)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != "per-section-coverage-1.0":
            raise ValueError("Unsupported PER section coverage schema_version")
        return value

    @field_validator("source_performance_baseline_uuid")
    @classmethod
    def normalize_source_baseline_uuid(cls, value: str) -> str:
        try:
            return UUID(value).hex
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(
                "source_performance_baseline_uuid must be a valid UUID"
            ) from exc

    @field_validator("owner_user_id")
    @classmethod
    def strip_owner_user_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("owner_user_id must not be blank")
        return value

    @model_validator(mode="after")
    def require_exact_canonical_order(self):
        section_ids = [section.section_id for section in self.sections]
        if section_ids != list(PER_CANONICAL_SECTION_IDS):
            raise ValueError(
                "PER section coverage must contain exactly the ten canonical sections in order"
            )
        return self


class PERSectionCoverageReport(BaseModel):
    """Frozen canonical section coverage exposed in a PER draft."""

    model_config = ConfigDict(extra="forbid")

    snapshot_ref: VersionedObjectReference
    sections: list[PERCanonicalSection]

    @model_validator(mode="after")
    def require_exact_canonical_order(self):
        section_ids = [section.section_id for section in self.sections]
        if section_ids != list(PER_CANONICAL_SECTION_IDS):
            raise ValueError(
                "PER section coverage must contain exactly the ten canonical sections in order"
            )
        return self

"""Typed models for deterministic, baseline-pinned PER reports."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


PER_SECTION_KEYS = (
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


class PERContentBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_key: str = Field(..., min_length=1)
    content: Any
    provenance: Literal["approved", "ai_generated", "system_generated"]
    source_object_uuid: str | None = None
    source_version: int | None = Field(default=None, ge=1)


class PERSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_key: Literal[
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
    ]
    title: str = Field(..., min_length=1)
    blocks: list[PERContentBlock] = Field(default_factory=list)


class PERTraceabilityEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_uuid: str
    object_type: str
    version: int = Field(..., ge=1)
    version_status: str


class PERCompletenessGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    section_key: str
    message: str
    severity: Literal["error", "warning"] = "error"


class PERReportPayload(BaseModel):
    """Canonical payload persisted in the generic Regulatory Object Store."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    report_type: Literal["PER", "PER-addendum"]
    product_uuid: str
    product_version: int = Field(..., ge=1)
    baseline_uuid: str
    sections: list[PERSection]
    traceability: list[PERTraceabilityEntry]
    completeness_gaps: list[PERCompletenessGap]


class PERReportCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_uuid: str
    report_type: Literal["PER", "PER-addendum"] = "PER"
    generated_by: str = Field(..., min_length=1)


class PERReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_uuid: str
    report_version: int = Field(..., ge=1)
    lifecycle_state: str
    payload: PERReportPayload

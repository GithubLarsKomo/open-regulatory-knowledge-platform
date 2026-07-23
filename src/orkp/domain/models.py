"""Domain models for regulatory objects — Product, Claim, Evidence.

These models define the structured payload schemas stored inside
the generic RegulatoryObject / ObjectVersion system.

Each domain model is a Pydantic BaseModel that gets serialized
as the `payload_json` column in `object_version`.

Unknown fields are rejected via ConfigDict(extra="forbid").
"""

from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Enums / Valid sets
# ---------------------------------------------------------------------------

PRODUCT_KINDS = {
    "assay",
    "reagent",
    "kit",
    "instrument",
    "software",
    "accessory",
    "specimen_receptacle",
    "calibrator",
    "control",
}

REGULATORY_STATUSES = {
    "development",
    "verification",
    "validation",
    "submitted",
    "registered",
    "marketed",
    "discontinued",
}

EVIDENCE_TYPES = {
    "literature",
    "clinical_study",
    "analytical_study",
    "scientific_validity",
    "internal_report",
    "external_report",
    "standard",
    "guideline",
    "regulation",
    "internal_document",
}

CLAIM_TYPES = {
    "regulatory",
    "clinical",
    "analytical",
    "performance",
    "safety",
    "marketing",
    "manufacturing",
    "software",
}

CLAIM_CATEGORIES = {
    "regulatory",
    "clinical",
    "analytical",
    "scientific",
    "marketing",
    "safety",
    "manufacturing",
    "software",
}

CLAIM_CONFIDENCE = {"high", "medium", "low"}

CLAIM_SEVERITY = {"high", "medium", "low"}


# ---------------------------------------------------------------------------
# Product domain
# ---------------------------------------------------------------------------


class ProductPayload(BaseModel):
    """Payload for a Product regulatory object (REQ-PROD-0001..0017)."""

    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    product_kind: str = Field(
        ...,
        description="assay|reagent|kit|instrument|software|accessory|specimen_receptacle|calibrator|control",
    )
    legal_manufacturer: str = Field(..., min_length=1)
    intended_purpose: str = Field(..., min_length=1)
    regulatory_status: str = Field(
        ...,
        description="development|verification|validation|submitted|registered|marketed|discontinued",
    )
    description: Optional[str] = None
    basic_udi_di: Optional[str] = None
    emdn_code: Optional[str] = None
    gmdn_code: Optional[str] = None
    ivr_code: Optional[str] = None
    manufacturer_srn: Optional[str] = None
    notified_body_number: Optional[str] = None
    risk_class: Optional[str] = None
    target_population: Optional[str] = None
    specimen_types: List[str] = []
    clinical_indications: Optional[str] = None
    contraindications: Optional[str] = None
    applicable_regulations: List[str] = []

    @field_validator("product_kind")
    @classmethod
    def _validate_kind(cls, v: str) -> str:
        if v not in PRODUCT_KINDS:
            raise ValueError(
                f"Invalid product_kind '{v}'. Must be one of: {', '.join(sorted(PRODUCT_KINDS))}"
            )
        return v

    @field_validator("regulatory_status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        if v not in REGULATORY_STATUSES:
            raise ValueError(
                f"Invalid regulatory_status '{v}'. Must be one of: {', '.join(sorted(REGULATORY_STATUSES))}"
            )
        return v

    @field_validator("applicable_regulations")
    @classmethod
    def _no_dup_regs(cls, v: List[str]) -> List[str]:
        if len(v) != len(set(v)):
            raise ValueError("applicable_regulations must not contain duplicates")
        return v

    @field_validator("specimen_types")
    @classmethod
    def _no_dup_specimens(cls, v: List[str]) -> List[str]:
        if len(v) != len(set(v)):
            raise ValueError("specimen_types must not contain duplicates")
        return v


class DevicePayload(BaseModel):
    """Payload for a Device variant regulatory object (REQ-PROD-0009)."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    device_kind: str = Field(...)
    udi_di: Optional[str] = None
    catalogue_number: Optional[str] = None
    configuration: Optional[str] = None
    software_version: Optional[str] = None
    market_status: Optional[str] = None


# ---------------------------------------------------------------------------
# Claim domain
# ---------------------------------------------------------------------------


class ClaimPayload(BaseModel):
    """Payload for a Claim regulatory object.

    evidence_links removed — claim-evidence traceability is stored
    exclusively through versioned object_relation rows.
    """

    model_config = ConfigDict(extra="forbid")

    claim_type: str = Field(
        ...,
        description="clinical|analytical|performance|regulatory|safety|marketing|manufacturing|software",
    )
    claim_category: str = Field(
        ...,
        description="regulatory|clinical|analytical|scientific|marketing|safety|manufacturing|software",
    )
    confidence: str = Field(..., description="high|medium|low")
    severity: str = Field(..., description="high|medium|low")
    jurisdiction: str = Field(...)
    language: str = Field(...)
    wording: str = Field(...)
    regulatory_scope: List[str] = []
    notes: Optional[str] = None

    @field_validator("claim_type")
    @classmethod
    def _validate_claim_type(cls, v: str) -> str:
        if v not in CLAIM_TYPES:
            raise ValueError(
                f"Invalid claim_type '{v}'. Must be one of: {', '.join(sorted(CLAIM_TYPES))}"
            )
        return v

    @field_validator("claim_category")
    @classmethod
    def _validate_claim_category(cls, v: str) -> str:
        if v not in CLAIM_CATEGORIES:
            raise ValueError(
                f"Invalid claim_category '{v}'. Must be one of: {', '.join(sorted(CLAIM_CATEGORIES))}"
            )
        return v

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: str) -> str:
        if v not in CLAIM_CONFIDENCE:
            raise ValueError("confidence must be 'high', 'medium' or 'low'")
        return v

    @field_validator("severity")
    @classmethod
    def _validate_severity(cls, v: str) -> str:
        if v not in CLAIM_SEVERITY:
            raise ValueError("severity must be 'high', 'medium' or 'low'")
        return v


# ---------------------------------------------------------------------------
# Evidence domain
# ---------------------------------------------------------------------------


class EvidencePayload(BaseModel):
    """Payload for an Evidence regulatory object."""

    model_config = ConfigDict(extra="forbid")

    evidence_type: str = Field(
        ...,
        description="literature|clinical_study|analytical_study|"
        "scientific_validity|internal_report|external_report|standard|guideline|regulation",
    )
    title: str = Field(..., min_length=1)
    source_reference: Optional[str] = None
    author: Optional[str] = None
    publication_date: Optional[str] = None
    journal: Optional[str] = None
    version: Optional[str] = None
    quality_rating: Optional[str] = None
    quality_notes: Optional[str] = None
    evidence_category: Optional[str] = None
    publication_status: Optional[str] = None
    keywords: List[str] = []
    checksum: Optional[str] = None

    @field_validator("evidence_type")
    @classmethod
    def _validate_ev_type(cls, v: str) -> str:
        if v not in EVIDENCE_TYPES:
            raise ValueError(
                f"Invalid evidence_type '{v}'. Must be one of: {', '.join(sorted(EVIDENCE_TYPES))}"
            )
        return v

    @field_validator("quality_rating")
    @classmethod
    def _validate_quality(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in {"high", "medium", "low"}:
            raise ValueError("quality_rating must be 'high', 'medium' or 'low'")
        return v

    @field_validator("publication_status")
    @classmethod
    def _validate_pub_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in {
            "published",
            "preprint",
            "unpublished",
            "confidential",
        }:
            raise ValueError(
                "publication_status must be 'published', 'preprint', 'unpublished' or 'confidential'"
            )
        return v

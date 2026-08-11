"""Strict content-provenance models for PER report authoring."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orkp.domain.risk_models import VersionedObjectReference


PER_SECTION_TYPES = {
    "scientific_validity",
    "analytical_performance",
    "clinical_performance",
}


class PERAIDraftBlockInput(BaseModel):
    """External AI draft text accepted only for baseline freezing."""

    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(..., min_length=1)
    section_type: str
    text: str = Field(..., min_length=1)
    model_id: str = Field(..., min_length=1)
    source_refs: list[VersionedObjectReference] = Field(..., min_length=1)

    @field_validator("block_id", "text", "model_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("block_id")
    @classmethod
    def reserve_approved_prefix(cls, value: str) -> str:
        if value.startswith("approved:"):
            raise ValueError("'approved:' is reserved for approved source blocks")
        return value

    @field_validator("section_type")
    @classmethod
    def validate_section_type(cls, value: str) -> str:
        if value not in PER_SECTION_TYPES:
            raise ValueError(f"Invalid PER section_type '{value}'")
        return value


class PERReportBaselineCreateRequest(BaseModel):
    """Create a derived report baseline with frozen report context."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    description: str | None = None
    performance_baseline_uuid: str = Field(..., min_length=1)
    ai_draft_blocks: list[PERAIDraftBlockInput] = Field(default_factory=list)
    benefit_risk_sources: list[VersionedObjectReference] = Field(default_factory=list)
    pmpf_assessments: list[VersionedObjectReference] = Field(default_factory=list)
    created_by_user_id: str = Field(..., min_length=1)

    @field_validator("name", "created_by_user_id", "performance_baseline_uuid")
    @classmethod
    def strip_required_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def reject_duplicate_references(self):
        block_ids = [block.block_id for block in self.ai_draft_blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError(
                "ai_draft_blocks must not contain duplicate block_id values"
            )
        for field_name, references in (
            ("benefit_risk_sources", self.benefit_risk_sources),
            ("pmpf_assessments", self.pmpf_assessments),
        ):
            keys = [(ref.object_uuid, ref.object_version) for ref in references]
            if len(keys) != len(set(keys)):
                raise ValueError(f"{field_name} must not contain duplicate references")
        return self


class PERReportBaselineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_uuid: str
    source_performance_baseline_uuid: str
    name: str
    description: str | None = None
    item_count: int
    ai_draft_block_count: int
    completeness_snapshot_ref: VersionedObjectReference
    section_coverage_snapshot_ref: VersionedObjectReference
    created_by_user_id: str


class PERReportContentPayload(BaseModel):
    """Persisted unapproved report text originating from an external AI system."""

    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(..., min_length=1)
    section_type: str
    text: str = Field(..., min_length=1)
    origin: str = "ai_draft"
    review_status: str = "unapproved_draft"
    model_id: str = Field(..., min_length=1)
    source_performance_baseline_uuid: str = Field(..., min_length=1)
    source_refs: list[VersionedObjectReference] = Field(..., min_length=1)
    owner_user_id: str = Field(..., min_length=1)

    @field_validator(
        "block_id",
        "text",
        "model_id",
        "source_performance_baseline_uuid",
        "owner_user_id",
    )
    @classmethod
    def strip_persisted_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("section_type")
    @classmethod
    def validate_persisted_section_type(cls, value: str) -> str:
        if value not in PER_SECTION_TYPES:
            raise ValueError(f"Invalid PER section_type '{value}'")
        return value

    @field_validator("origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        if value != "ai_draft":
            raise ValueError("report_content origin must be 'ai_draft'")
        return value

    @field_validator("review_status")
    @classmethod
    def validate_review_status(cls, value: str) -> str:
        if value != "unapproved_draft":
            raise ValueError("AI report_content must remain 'unapproved_draft'")
        return value


class PERContentBlock(BaseModel):
    """Explicit provenance marker for text exposed in a PER draft."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    section_type: str
    text: str
    origin: str
    review_status: str
    source_refs: list[VersionedObjectReference]
    content_ref: VersionedObjectReference | None = None
    model_id: str | None = None

    @model_validator(mode="after")
    def validate_provenance_contract(self):
        if self.origin == "approved_source":
            if self.review_status != "source_approved":
                raise ValueError(
                    "approved_source content requires source_approved status"
                )
            if self.model_id is not None:
                raise ValueError("approved_source content cannot carry model_id")
            if self.content_ref is not None:
                raise ValueError("approved_source content cannot carry content_ref")
        elif self.origin == "ai_draft":
            if self.review_status != "unapproved_draft":
                raise ValueError("ai_draft content requires unapproved_draft status")
            if not self.model_id:
                raise ValueError("ai_draft content requires model_id")
            if self.content_ref is None:
                raise ValueError("ai_draft content requires frozen content_ref")
        else:
            raise ValueError(f"Unknown content origin '{self.origin}'")
        return self

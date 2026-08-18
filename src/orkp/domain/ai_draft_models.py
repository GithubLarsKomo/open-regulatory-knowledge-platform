"""Strict provider-neutral models for auditable grounded AI draft records."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orkp.domain.risk_ai_policy import RiskAIDraftContent
from orkp.domain.risk_models import VersionedObjectReference


AIStatementKind = Literal["retrieved_fact", "inference", "generated_wording"]
AITargetDomain = Literal["general", "risk"]


class AIDraftBlock(BaseModel):
    """One explicitly classified, grounded statement in an AI draft."""

    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(..., min_length=1)
    statement_kind: AIStatementKind
    text: str = Field(..., min_length=1)
    source_refs: list[VersionedObjectReference] = Field(..., min_length=1)

    @field_validator("block_id", "text")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def reject_duplicate_sources(self):
        keys = [(ref.object_uuid, ref.object_version) for ref in self.source_refs]
        if len(keys) != len(set(keys)):
            raise ValueError("AI draft block must not contain duplicate source refs")
        return self


class AIDraftCreateRequest(BaseModel):
    """External/provider result submitted to the governed AI persistence boundary."""

    model_config = ConfigDict(extra="forbid")

    prompt_text: str = Field(..., min_length=1)
    model_id: str = Field(..., min_length=1)
    context_refs: list[VersionedObjectReference] = Field(..., min_length=1)
    blocks: list[AIDraftBlock] = Field(..., min_length=1)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    initiated_by_user_id: str = Field(..., min_length=1)
    target_domain: AITargetDomain = "general"
    risk_support: dict[str, Any] | None = None

    @field_validator("prompt_text", "model_id", "initiated_by_user_id")
    @classmethod
    def strip_required_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def validate_grounding_contract(self):
        context_keys = [
            (ref.object_uuid, ref.object_version) for ref in self.context_refs
        ]
        if len(context_keys) != len(set(context_keys)):
            raise ValueError("context_refs must not contain duplicate exact references")
        allowed = set(context_keys)
        block_ids = [block.block_id for block in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError(
                "AI draft blocks must not contain duplicate block_id values"
            )
        for block in self.blocks:
            keys = {(ref.object_uuid, ref.object_version) for ref in block.source_refs}
            if not keys.issubset(allowed):
                raise ValueError(
                    f"AI draft block '{block.block_id}' cites a source outside context_refs"
                )
        if self.target_domain == "risk":
            non_facts = [
                block.block_id
                for block in self.blocks
                if block.statement_kind != "retrieved_fact"
            ]
            if non_facts:
                raise ValueError(
                    "Risk-targeted AI-derived wording/inference must use structured "
                    "risk_support; non-fact blocks: " + ", ".join(non_facts)
                )
        elif self.risk_support is not None:
            raise ValueError("risk_support requires target_domain='risk'")
        return self


class AIDraftRegenerateRequest(AIDraftCreateRequest):
    """Create a new version of an existing mutable AI draft."""

    actor_user_id: str = Field(..., min_length=1)

    @field_validator("actor_user_id")
    @classmethod
    def strip_actor(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class AIDraftPayload(BaseModel):
    """Persisted exact-version AI draft audit payload."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-draft-1.0"] = "ai-draft-1.0"
    regulatory_status: Literal["unapproved_draft"] = "unapproved_draft"
    approval_authority: Literal["human_workflow"] = "human_workflow"
    ai_may_approve: Literal[False] = False
    prompt_text: str = Field(..., min_length=1)
    model_id: str = Field(..., min_length=1)
    context_refs: list[VersionedObjectReference] = Field(..., min_length=1)
    blocks: list[AIDraftBlock] = Field(..., min_length=1)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    initiated_by_user_id: str = Field(..., min_length=1)
    target_domain: AITargetDomain = "general"
    risk_support: RiskAIDraftContent | None = None

    @field_validator("prompt_text", "model_id", "initiated_by_user_id")
    @classmethod
    def strip_persisted_required_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def validate_persisted_grounding(self):
        context_keys = [
            (ref.object_uuid, ref.object_version) for ref in self.context_refs
        ]
        if len(context_keys) != len(set(context_keys)):
            raise ValueError("context_refs must not contain duplicate exact references")
        allowed = set(context_keys)
        block_ids = [block.block_id for block in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError(
                "AI draft blocks must not contain duplicate block_id values"
            )
        for block in self.blocks:
            keys = {(ref.object_uuid, ref.object_version) for ref in block.source_refs}
            if not keys.issubset(allowed):
                raise ValueError(
                    f"AI draft block '{block.block_id}' cites a source outside context_refs"
                )
        if self.target_domain == "risk":
            non_facts = [
                block.block_id
                for block in self.blocks
                if block.statement_kind != "retrieved_fact"
            ]
            if non_facts:
                raise ValueError(
                    "Risk-targeted AI-derived wording/inference must use structured "
                    "risk_support; non-fact blocks: " + ", ".join(non_facts)
                )
        elif self.risk_support is not None:
            raise ValueError("risk_support requires target_domain='risk'")
        return self


class AIDraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_uuid: str
    object_version: int = Field(..., ge=1)
    lifecycle_state: Literal["draft"]
    owner_user_id: str
    payload: AIDraftPayload

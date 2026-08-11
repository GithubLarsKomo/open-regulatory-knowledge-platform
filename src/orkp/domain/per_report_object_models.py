"""Strict persisted PER report aggregate models."""

import hashlib
import json
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orkp.domain.per_draft_models import PERDraftPayload
from orkp.domain.risk_models import VersionedObjectReference


PER_REPORT_TYPES = {"PER", "PER-addendum"}


def canonicalize_per_draft(draft: PERDraftPayload) -> str:
    """Return the deterministic canonical JSON representation of a PER draft."""
    return json.dumps(
        draft.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class PERReportObjectPayload(BaseModel):
    """Versioned payload stored in the Core RegulatoryObject store."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "per-report-object-1.0"
    report_type: str = "PER"
    product: VersionedObjectReference
    baseline_uuid: str
    draft: PERDraftPayload
    canonical_checksum_sha256: str
    predecessor_report: VersionedObjectReference | None = None

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != "per-report-object-1.0":
            raise ValueError("Unsupported persisted PER report schema_version")
        return value

    @field_validator("report_type")
    @classmethod
    def validate_report_type(cls, value: str) -> str:
        if value not in PER_REPORT_TYPES:
            raise ValueError(f"Invalid PER report_type '{value}'")
        return value

    @field_validator("baseline_uuid")
    @classmethod
    def normalize_baseline_uuid(cls, value: str) -> str:
        try:
            return UUID(value).hex
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("baseline_uuid must be a valid UUID") from exc

    @field_validator("canonical_checksum_sha256")
    @classmethod
    def validate_checksum(cls, value: str) -> str:
        value = value.lower()
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError("canonical_checksum_sha256 must be 64 lowercase hex characters")
        return value

    @model_validator(mode="after")
    def validate_frozen_contract(self):
        if self.draft.schema_version != "per-draft-1.3":
            raise ValueError("Persisted PER report requires governed per-draft-1.3")
        if self.draft.completeness_report is None or self.draft.section_coverage is None:
            raise ValueError(
                "Persisted PER report requires completeness and canonical section coverage"
            )
        if self.draft.baseline_uuid != self.baseline_uuid:
            raise ValueError("PER report baseline_uuid must match frozen draft baseline_uuid")
        if (
            self.draft.product.object_uuid != self.product.object_uuid
            or self.draft.product.object_version != self.product.object_version
        ):
            raise ValueError("PER report Product must match frozen draft Product")
        canonical = canonicalize_per_draft(self.draft)
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if self.canonical_checksum_sha256 != expected:
            raise ValueError("PER report canonical checksum does not match frozen draft")
        return self


class PERReportCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_uuid: str = Field(..., min_length=1)
    baseline_uuid: str = Field(..., min_length=1)
    report_type: str = "PER"
    owner_user_id: str = Field(..., min_length=1)

    @field_validator("product_uuid", "baseline_uuid")
    @classmethod
    def normalize_uuid(cls, value: str) -> str:
        try:
            return UUID(value).hex
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("must be a valid UUID") from exc

    @field_validator("report_type")
    @classmethod
    def validate_create_report_type(cls, value: str) -> str:
        if value not in PER_REPORT_TYPES:
            raise ValueError(f"Invalid PER report_type '{value}'")
        return value

    @field_validator("owner_user_id")
    @classmethod
    def strip_owner(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("owner_user_id must not be blank")
        return value


class PERReportRegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_uuid: str = Field(..., min_length=1)
    actor_user_id: str = Field(..., min_length=1)

    @field_validator("baseline_uuid")
    @classmethod
    def normalize_regeneration_baseline(cls, value: str) -> str:
        try:
            return UUID(value).hex
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("baseline_uuid must be a valid UUID") from exc

    @field_validator("actor_user_id")
    @classmethod
    def strip_actor(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("actor_user_id must not be blank")
        return value


class PERReportLifecycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_user_id: str = Field(..., min_length=1)
    comments: str | None = None

    @field_validator("actor_user_id")
    @classmethod
    def strip_lifecycle_actor(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("actor_user_id must not be blank")
        return value


class PERReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_uuid: str
    object_version: int
    lifecycle_state: str
    owner_user_id: str
    report_type: str
    product: VersionedObjectReference
    baseline_uuid: str
    canonical_checksum_sha256: str
    predecessor_report: VersionedObjectReference | None = None
    draft: PERDraftPayload


class PERReportCanonicalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_uuid: str
    object_version: int
    canonical_checksum_sha256: str
    canonical_json: str

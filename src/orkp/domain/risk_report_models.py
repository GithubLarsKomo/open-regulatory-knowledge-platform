"""Strict models for reproducible Risk Management Report baselines."""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from orkp.domain.risk_models import VersionedObjectReference


class RiskReportBaselineCreateRequest(BaseModel):
    """Freeze exact object versions for a reproducible Risk Management Report."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    objects: list[VersionedObjectReference] = Field(..., min_length=1)
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
    def strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class RiskReportBaselineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_uuid: str
    name: str
    description: Optional[str] = None
    item_count: int
    created_by_user_id: str


class RiskReportItemSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_uuid: str
    object_type: str
    object_version: int
    snapshot: dict[str, Any]


class RiskReportPayload(BaseModel):
    """Canonical deterministic report representation derived only from a baseline."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "risk-report-1.0"
    baseline_uuid: str
    baseline_name: str
    baseline_description: Optional[str] = None
    items: list[RiskReportItemSnapshot]


class RiskReportGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_by_user_id: str = Field(..., min_length=1)

    @field_validator("generated_by_user_id")
    @classmethod
    def strip_generated_by(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class RiskReportGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_uuid: str
    baseline_uuid: str
    checksum_sha256: str
    canonical_json: str
    format: str = "json"
    report: RiskReportPayload

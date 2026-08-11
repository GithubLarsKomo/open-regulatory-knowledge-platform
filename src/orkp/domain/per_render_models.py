"""Strict models for deterministic PER document rendering."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


PER_RENDER_FORMATS = {"html", "docx", "pdf"}


class PERRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_by_user_id: str = Field(..., min_length=1)

    @field_validator("generated_by_user_id")
    @classmethod
    def strip_generated_by(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class PERRenderResult(BaseModel):
    """Internal render result returned by the rendering service."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    artifact_uuid: str
    baseline_uuid: str
    format: str
    media_type: str
    filename: str
    checksum_sha256: str
    content: bytes

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        if value not in PER_RENDER_FORMATS:
            raise ValueError(f"Unsupported PER render format '{value}'")
        return value

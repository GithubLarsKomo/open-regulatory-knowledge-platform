"""Strict models for post-market safety information and Risk Impact Assessment."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orkp.domain.risk_models import VersionedObjectReference

PostMarketSourceType = Literal[
    "complaint",
    "vigilance",
    "pmpf",
    "literature",
    "trend",
    "field_safety",
    "other",
]
RiskImpactOutcome = Literal[
    "pending",
    "no_change",
    "review_required",
    "risk_increase",
    "new_risk_identified",
    "control_effectiveness_concern",
]


class PostMarketInformationCreateRequest(BaseModel):
    """Create exact-version post-market information for a Risk Analysis."""

    model_config = ConfigDict(extra="forbid")
    risk_analysis: VersionedObjectReference
    source_type: PostMarketSourceType
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    observed_at: str
    reported_by_user_id: str = Field(..., min_length=1)
    external_reference: Optional[str] = None

    @field_validator("title", "description", "observed_at", "reported_by_user_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("external_reference")
    @classmethod
    def strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class PostMarketInformationPayload(PostMarketInformationCreateRequest):
    """Persisted post-market information payload."""

    information_id: str = Field(..., min_length=1)
    received_at: str


class RiskImpactAssessmentDraftPayload(BaseModel):
    """Version-pinned pending or completed Risk Impact Assessment payload."""

    model_config = ConfigDict(extra="forbid")
    assessment_id: str = Field(..., min_length=1)
    risk_analysis: VersionedObjectReference
    post_market_information: VersionedObjectReference
    outcome: RiskImpactOutcome = "pending"
    rationale: Optional[str] = None
    requires_risk_review: bool = True
    assessor_user_id: Optional[str] = None
    assessed_at: Optional[str] = None

    @model_validator(mode="after")
    def validate_decision_state(self):
        if self.outcome == "pending":
            if any(
                value is not None
                for value in (self.rationale, self.assessor_user_id, self.assessed_at)
            ):
                raise ValueError(
                    "pending assessment must not contain a completed decision"
                )
            if not self.requires_risk_review:
                raise ValueError("pending assessment must require risk review")
            return self

        if (
            not self.rationale
            or not self.rationale.strip()
            or not self.assessor_user_id
            or not self.assessor_user_id.strip()
            or not self.assessed_at
            or not self.assessed_at.strip()
        ):
            raise ValueError(
                "completed assessment requires rationale, assessor_user_id and assessed_at"
            )

        expected_review = self.outcome != "no_change"
        if self.requires_risk_review != expected_review:
            raise ValueError(
                "requires_risk_review must be false only for no_change outcomes"
            )
        return self


class RiskImpactAssessmentCompleteRequest(BaseModel):
    """Human impact decision for a pending Risk Impact Assessment."""

    model_config = ConfigDict(extra="forbid")
    outcome: Literal[
        "no_change",
        "review_required",
        "risk_increase",
        "new_risk_identified",
        "control_effectiveness_concern",
    ]
    rationale: str = Field(..., min_length=1)
    assessor_user_id: str = Field(..., min_length=1)

    @field_validator("rationale", "assessor_user_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @property
    def requires_risk_review(self) -> bool:
        return self.outcome != "no_change"


class PostMarketInformationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_uuid: str
    object_version: int
    lifecycle_state: str
    payload: PostMarketInformationPayload


class RiskImpactAssessmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_uuid: str
    object_version: int
    lifecycle_state: str
    payload: RiskImpactAssessmentDraftPayload


class PostMarketIngestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    information: PostMarketInformationResponse
    impact_assessment: RiskImpactAssessmentResponse

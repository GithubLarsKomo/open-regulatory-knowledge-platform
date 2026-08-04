"""
Strict Pydantic payload models for persisted Risk Policy and Evaluations.
Uses ConfigDict(extra="forbid") for all models.
"""

from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


SEVERITY_LEVELS = {"negligible", "minor", "moderate", "critical", "catastrophic"}
PROBABILITY_LEVELS = {"improbable", "unlikely", "possible", "likely", "probable"}
RISK_CONTROL_OPTIONS = {
    "design_by_safety",
    "protective_measure",
    "information_for_safety",
}
CONTROL_IMPLEMENTATION_STATUS = {"proposed", "implemented"}
VERIFICATION_METHODS = {
    "test",
    "inspection",
    "analysis",
    "review",
    "simulation",
    "usability_validation",
    "clinical_evaluation",
    "production_validation",
    "other",
}
EFFECTIVENESS_RESULTS = {
    "effective",
    "partially_effective",
    "ineffective",
    "inconclusive",
}
VERIFICATION_CONCLUSIONS = {"passed", "passed_with_limitations", "failed"}
BENEFIT_RISK_CONCLUSION = {"favorable", "unfavorable", "inconclusive"}
REQUIRED_ACTIONS = {
    "none",
    "monitor",
    "control_required",
    "benefit_risk_required",
    "prohibited",
}
POLICY_LIFECYCLE = {"draft", "in_review", "approved", "effective", "obsolete"}


def _uuid_hex(value: str) -> str:
    try:
        return UUID(value).hex
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("must be a valid UUID") from exc


class VersionedObjectReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_uuid: str
    object_version: int = Field(..., ge=1)

    @field_validator("object_uuid")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        return _uuid_hex(value)


class RiskPolicyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    policy_version: str = Field(..., min_length=1)
    severity_scale: List[str] = Field(..., min_length=1)
    probability_scale: List[str] = Field(..., min_length=1)
    risk_levels: List[str] = Field(..., min_length=1)
    risk_matrix: Dict[str, Dict[str, str]]
    acceptability_rules: Dict[str, bool]
    required_actions: Dict[str, str]
    control_hierarchy: List[str] = Field(..., min_length=1)
    benefit_risk_required_for: List[str] = Field(default_factory=list)
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None
    jurisdiction: List[str] = Field(default_factory=list)
    product_scope: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class InitialRiskEvaluationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_id: str = Field(..., min_length=1)
    risk_analysis_uuid: str = Field(..., min_length=1)
    risk_analysis_version: int = Field(..., ge=1)
    severity: str
    probability: str
    calculated_risk_level: str
    acceptable: bool
    action_required: str
    risk_policy_uuid: str = Field(..., min_length=1)
    risk_policy_version: int = Field(..., ge=1)
    policy_revision: str = Field(..., min_length=1)
    evaluator_user_id: str = Field(..., min_length=1)
    rationale: Optional[str] = None
    assumptions: Optional[str] = None
    uncertainty: Optional[str] = None
    evaluated_at: str

    @field_validator("risk_analysis_uuid", "risk_policy_uuid")
    @classmethod
    def validate_uuids(cls, value: str) -> str:
        return _uuid_hex(value)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        if value not in SEVERITY_LEVELS:
            raise ValueError(f"Invalid severity '{value}'")
        return value

    @field_validator("probability")
    @classmethod
    def validate_probability(cls, value: str) -> str:
        if value not in PROBABILITY_LEVELS:
            raise ValueError(f"Invalid probability '{value}'")
        return value


class InitialRiskEvaluationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_analysis_version: int = Field(..., ge=1)
    risk_policy_uuid: str
    risk_policy_version: int = Field(..., ge=1)
    severity: str
    probability: str
    evaluator_user_id: str = Field(..., min_length=1)
    rationale: Optional[str] = None
    assumptions: Optional[str] = None
    uncertainty: Optional[str] = None

    @field_validator("risk_policy_uuid")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        return _uuid_hex(value)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        if value not in SEVERITY_LEVELS:
            raise ValueError(f"Invalid severity '{value}'")
        return value

    @field_validator("probability")
    @classmethod
    def validate_probability(cls, value: str) -> str:
        if value not in PROBABILITY_LEVELS:
            raise ValueError(f"Invalid probability '{value}'")
        return value


class ResidualRiskEvaluationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_id: str = Field(..., min_length=1)
    risk_analysis_uuid: str
    risk_analysis_version: int = Field(..., ge=1)
    initial_evaluation_uuid: str
    initial_evaluation_version: int = Field(..., ge=1)
    control_verifications: List[VersionedObjectReference] = Field(..., min_length=1)
    residual_severity: str
    residual_probability: str
    calculated_risk_level: str
    acceptable: bool
    action_required: str
    severity_improved: bool
    probability_improved: bool
    severity_worsened: bool
    probability_worsened: bool
    risk_level_improved: bool
    reduced: bool
    regression_detected: bool
    benefit_risk_required: bool
    risk_policy_uuid: str
    risk_policy_version: int = Field(..., ge=1)
    policy_revision: str = Field(..., min_length=1)
    evaluator_user_id: str = Field(..., min_length=1)
    rationale: Optional[str] = None
    evaluated_at: str

    @field_validator(
        "risk_analysis_uuid", "initial_evaluation_uuid", "risk_policy_uuid"
    )
    @classmethod
    def validate_uuids(cls, value: str) -> str:
        return _uuid_hex(value)

    @field_validator("residual_severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        if value not in SEVERITY_LEVELS:
            raise ValueError(f"Invalid severity '{value}'")
        return value

    @field_validator("residual_probability")
    @classmethod
    def validate_probability(cls, value: str) -> str:
        if value not in PROBABILITY_LEVELS:
            raise ValueError(f"Invalid probability '{value}'")
        return value


class ResidualRiskEvaluationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_analysis_version: int = Field(..., ge=1)
    initial_evaluation_uuid: str
    initial_evaluation_version: int = Field(..., ge=1)
    control_verifications: List[VersionedObjectReference] = Field(..., min_length=1)
    residual_severity: str
    residual_probability: str
    evaluator_user_id: str = Field(..., min_length=1)
    rationale: Optional[str] = None

    @field_validator("initial_evaluation_uuid")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        return _uuid_hex(value)

    @field_validator("residual_severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        if value not in SEVERITY_LEVELS:
            raise ValueError(f"Invalid severity '{value}'")
        return value

    @field_validator("residual_probability")
    @classmethod
    def validate_probability(cls, value: str) -> str:
        if value not in PROBABILITY_LEVELS:
            raise ValueError(f"Invalid probability '{value}'")
        return value

    @model_validator(mode="after")
    def reject_duplicate_verifications(self):
        keys = {
            (ref.object_uuid, ref.object_version) for ref in self.control_verifications
        }
        if len(keys) != len(self.control_verifications):
            raise ValueError("control_verifications must not contain duplicates")
        return self


class ControlVerificationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_analysis: VersionedObjectReference
    risk_control: VersionedObjectReference
    initial_evaluation: VersionedObjectReference
    risk_policy: VersionedObjectReference
    evidence: List[VersionedObjectReference] = Field(..., min_length=1)
    verification_method: str
    verification_scope: str = Field(..., min_length=1)
    implementation_verified: bool
    effectiveness_verified: bool
    no_new_uncontrolled_risks: bool
    effectiveness_result: str
    conclusion: str
    deviations: Optional[str] = None
    limitations: Optional[str] = None
    verified_by_user_id: str = Field(..., min_length=1)

    @field_validator("verification_scope", "verified_by_user_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("verification_method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        if value not in VERIFICATION_METHODS:
            raise ValueError(f"Invalid verification method '{value}'")
        return value

    @field_validator("effectiveness_result")
    @classmethod
    def validate_effectiveness(cls, value: str) -> str:
        if value not in EFFECTIVENESS_RESULTS:
            raise ValueError(f"Invalid effectiveness result '{value}'")
        return value

    @field_validator("conclusion")
    @classmethod
    def validate_conclusion(cls, value: str) -> str:
        if value not in VERIFICATION_CONCLUSIONS:
            raise ValueError(f"Invalid conclusion '{value}'")
        return value

    @model_validator(mode="after")
    def validate_consistency(self):
        if self.conclusion == "passed":
            if not all(
                (
                    self.implementation_verified,
                    self.effectiveness_verified,
                    self.no_new_uncontrolled_risks,
                )
            ):
                raise ValueError("passed verification requires all verification flags")
            if self.effectiveness_result != "effective":
                raise ValueError("passed verification requires effective result")
        if self.conclusion == "passed_with_limitations" and not (
            self.limitations and self.limitations.strip()
        ):
            raise ValueError("passed_with_limitations requires limitations")
        if (
            self.conclusion == "failed"
            and all(
                (
                    self.implementation_verified,
                    self.effectiveness_verified,
                    self.no_new_uncontrolled_risks,
                    self.effectiveness_result == "effective",
                )
            )
            and not (self.deviations and self.deviations.strip())
        ):
            raise ValueError(
                "failed verification requires a deviation or negative result"
            )
        keys = {(ref.object_uuid, ref.object_version) for ref in self.evidence}
        if len(keys) != len(self.evidence):
            raise ValueError("evidence must not contain duplicates")
        return self


class ControlVerificationPayload(ControlVerificationCreateRequest):
    verification_id: str = Field(..., min_length=1)
    verified_at: str


class BenefitRiskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: str = Field(..., min_length=1)
    benefits: str = Field(..., min_length=1)
    residual_risks: Optional[str] = None
    rationale: str = Field(..., min_length=1)
    conclusion: str

    @field_validator("conclusion")
    @classmethod
    def validate_conclusion(cls, value: str) -> str:
        if value not in BENEFIT_RISK_CONCLUSION:
            raise ValueError(f"Invalid benefit-risk conclusion '{value}'")
        return value


class InitialRiskEvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_uuid: str
    object_version: int
    lifecycle_state: str
    payload: InitialRiskEvaluationPayload


class ResidualRiskEvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_uuid: str
    object_version: int
    lifecycle_state: str
    payload: ResidualRiskEvaluationPayload


class ControlVerificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_uuid: str
    object_version: int
    lifecycle_state: str
    eligible_for_residual_evaluation: bool
    payload: ControlVerificationPayload

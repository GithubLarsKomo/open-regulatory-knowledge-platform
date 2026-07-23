"""
Strict Pydantic payload models for persisted Risk Policy and Evaluations.
Uses ConfigDict(extra="forbid") for all models.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

SEVERITY_LEVELS = {"negligible", "minor", "moderate", "critical", "catastrophic"}
PROBABILITY_LEVELS = {"improbable", "unlikely", "possible", "likely", "probable"}
RISK_CONTROL_OPTIONS = {
    "design_by_safety",
    "protective_measure",
    "information_for_safety",
}
CONTROL_IMPLEMENTATION_STATUS = {"proposed", "implemented"}
VERIFICATION_STATUS = {"draft", "executed", "in_review", "approved", "rejected"}
VERIFICATION_CONCLUSION = {"passed", "failed", "inconclusive"}
BENEFIT_RISK_CONCLUSION = {"favorable", "unfavorable", "inconclusive"}
REQUIRED_ACTIONS = {
    "none",
    "monitor",
    "control_required",
    "benefit_risk_required",
    "prohibited",
}
POLICY_LIFECYCLE = {"draft", "in_review", "approved", "effective", "obsolete"}


# ---------------------------------------------------------------------------
# Risk Policy
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Initial Risk Evaluation
# ---------------------------------------------------------------------------


class InitialRiskEvaluationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_id: str = Field(..., min_length=1)
    risk_analysis_uuid: str = Field(..., min_length=1)
    risk_analysis_version: int = Field(..., ge=1)
    severity: str = Field(...)
    probability: str = Field(...)
    calculated_risk_level: str = Field(...)
    acceptable: bool = Field(...)
    action_required: str = Field(...)
    risk_policy_uuid: str = Field(..., min_length=1)
    risk_policy_version: int = Field(..., ge=1)
    policy_revision: str = Field(..., min_length=1)
    evaluator_user_id: str = Field(..., min_length=1)
    rationale: Optional[str] = None
    assumptions: Optional[str] = None
    uncertainty: Optional[str] = None
    evaluated_at: str = Field(...)

    @field_validator("severity")
    @classmethod
    def _validate_severity(cls, v: str) -> str:
        if v not in SEVERITY_LEVELS:
            raise ValueError(f"Invalid severity '{v}'")
        return v

    @field_validator("probability")
    @classmethod
    def _validate_probability(cls, v: str) -> str:
        if v not in PROBABILITY_LEVELS:
            raise ValueError(f"Invalid probability '{v}'")
        return v


class InitialRiskEvaluationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_analysis_version: int = Field(..., ge=1)
    risk_policy_uuid: str = Field(..., min_length=1)
    risk_policy_version: int = Field(..., ge=1)
    severity: str = Field(...)
    probability: str = Field(...)
    evaluator_user_id: str = Field(..., min_length=1)
    rationale: Optional[str] = None
    assumptions: Optional[str] = None
    uncertainty: Optional[str] = None

    @field_validator("severity")
    @classmethod
    def _validate_severity(cls, v: str) -> str:
        if v not in SEVERITY_LEVELS:
            raise ValueError(f"Invalid severity '{v}'")
        return v

    @field_validator("probability")
    @classmethod
    def _validate_probability(cls, v: str) -> str:
        if v not in PROBABILITY_LEVELS:
            raise ValueError(f"Invalid probability '{v}'")
        return v


# ---------------------------------------------------------------------------
# Residual Risk Evaluation
# ---------------------------------------------------------------------------


class ResidualRiskEvaluationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_id: str = Field(..., min_length=1)
    risk_analysis_uuid: str = Field(..., min_length=1)
    risk_analysis_version: int = Field(..., ge=1)
    initial_evaluation_uuid: str = Field(..., min_length=1)
    initial_evaluation_version: int = Field(..., ge=1)
    residual_severity: str = Field(...)
    residual_probability: str = Field(...)
    calculated_risk_level: str = Field(...)
    acceptable: bool = Field(...)
    action_required: str = Field(...)
    severity_improved: bool = Field(...)
    probability_improved: bool = Field(...)
    severity_worsened: bool = Field(...)
    probability_worsened: bool = Field(...)
    risk_level_improved: bool = Field(...)
    reduced: bool = Field(...)
    regression_detected: bool = Field(...)
    benefit_risk_required: bool = Field(...)
    risk_policy_uuid: str = Field(..., min_length=1)
    risk_policy_version: int = Field(..., ge=1)
    policy_revision: str = Field(..., min_length=1)
    evaluator_user_id: str = Field(..., min_length=1)
    rationale: Optional[str] = None
    evaluated_at: str = Field(...)

    @field_validator("residual_severity")
    @classmethod
    def _validate_rsev(cls, v: str) -> str:
        if v not in SEVERITY_LEVELS:
            raise ValueError(f"Invalid severity '{v}'")
        return v

    @field_validator("residual_probability")
    @classmethod
    def _validate_rprob(cls, v: str) -> str:
        if v not in PROBABILITY_LEVELS:
            raise ValueError(f"Invalid probability '{v}'")
        return v


class ResidualRiskEvaluationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_analysis_version: int = Field(..., ge=1)
    initial_evaluation_uuid: str = Field(..., min_length=1)
    initial_evaluation_version: int = Field(..., ge=1)
    residual_severity: str = Field(...)
    residual_probability: str = Field(...)
    evaluator_user_id: str = Field(..., min_length=1)
    rationale: Optional[str] = None

    @field_validator("residual_severity")
    @classmethod
    def _validate_rsev(cls, v: str) -> str:
        if v not in SEVERITY_LEVELS:
            raise ValueError(f"Invalid severity '{v}'")
        return v

    @field_validator("residual_probability")
    @classmethod
    def _validate_rprob(cls, v: str) -> str:
        if v not in PROBABILITY_LEVELS:
            raise ValueError(f"Invalid probability '{v}'")
        return v


# ---------------------------------------------------------------------------
# Control Verification
# ---------------------------------------------------------------------------


class ControlVerificationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verification_id: str = Field(..., min_length=1)
    method: str = Field(..., min_length=1)
    protocol_reference: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    result_summary: Optional[str] = None
    conclusion: str = Field(...)
    verification_status: str = Field(...)
    author_user_id: str = Field(..., min_length=1)
    reviewer_user_id: Optional[str] = None
    verification_date: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("conclusion")
    @classmethod
    def _validate_conclusion(cls, v: str) -> str:
        if v not in VERIFICATION_CONCLUSION:
            raise ValueError(f"Invalid conclusion '{v}'")
        return v

    @field_validator("verification_status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        if v not in VERIFICATION_STATUS:
            raise ValueError(f"Invalid verification status '{v}'")
        return v


# ---------------------------------------------------------------------------
# Benefit-Risk
# ---------------------------------------------------------------------------


class BenefitRiskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: str = Field(..., min_length=1)
    benefits: str = Field(..., min_length=1)
    residual_risks: Optional[str] = None
    rationale: str = Field(..., min_length=1)
    conclusion: str = Field(...)

    @field_validator("conclusion")
    @classmethod
    def _validate_conclusion(cls, v: str) -> str:
        if v not in BENEFIT_RISK_CONCLUSION:
            raise ValueError(f"Invalid benefit-risk conclusion '{v}'")
        return v


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


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

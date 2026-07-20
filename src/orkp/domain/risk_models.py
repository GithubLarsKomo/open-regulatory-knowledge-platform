"""
Strict Pydantic payload models for the Risk Management domain.

Uses ConfigDict(extra="forbid") for all models.
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

HAZARD_CATEGORIES = {
    'biological', 'chemical', 'electrical', 'energy', 'information',
    'mechanical', 'radiation', 'thermal', 'use_error',
}

HARM_CATEGORIES = {
    'death', 'injury', 'infection', 'misdiagnosis', 'delay_in_treatment',
    'psychological', 'economic',
}

SEVERITY_LEVELS = {'negligible', 'minor', 'moderate', 'critical', 'catastrophic'}
PROBABILITY_LEVELS = {'improbable', 'unlikely', 'possible', 'likely', 'probable'}
RISK_ACCEPTABILITY = {'acceptable', 'unacceptable', 'as_low_as_reasonably_practicable'}
RISK_CONTROL_OPTIONS = {'design_by_safety', 'protective_measure', 'information_for_safety'}
CONTROL_IMPLEMENTATION_STATUS = {'proposed', 'implemented', 'verified'}
BENEFIT_RISK_CONCLUSION = {'favorable', 'unfavorable', 'inconclusive'}


# ---------------------------------------------------------------------------
# Hazard
# ---------------------------------------------------------------------------

class HazardPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hazard_id: str = Field(..., min_length=1)
    category: str = Field(..., description="biological|chemical|electrical|energy|information|mechanical|radiation|thermal|use_error")
    description: str = Field(..., min_length=1)
    source: Optional[str] = None
    foreseeable_misuse: Optional[str] = None

    @field_validator('category')
    @classmethod
    def _validate_category(cls, v: str) -> str:
        if v not in HAZARD_CATEGORIES:
            raise ValueError(f"Invalid hazard category '{v}'")
        return v


class SequenceOfEventsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence_id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    initiating_event: Optional[str] = None
    intermediate_events: List[str] = []
    foreseeable_conditions: Optional[str] = None


class HazardousSituationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    situation_id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    exposed_persons: Optional[str] = None
    exposure_context: Optional[str] = None


class HarmPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    harm_id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    harm_category: str = Field(..., description="death|injury|infection|misdiagnosis|delay_in_treatment|psychological|economic")
    clinical_consequence: Optional[str] = None

    @field_validator('harm_category')
    @classmethod
    def _validate_harm_category(cls, v: str) -> str:
        if v not in HARM_CATEGORIES:
            raise ValueError(f"Invalid harm category '{v}'")
        return v


# ---------------------------------------------------------------------------
# Risk Analysis
# ---------------------------------------------------------------------------

class RiskAnalysisPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    rationale: Optional[str] = None
    severity: str = Field(..., description="negligible|minor|moderate|critical|catastrophic")
    probability: str = Field(..., description="improbable|unlikely|possible|likely|probable")
    risk_level: Optional[str] = None
    acceptability: Optional[str] = None
    estimation_method: Optional[str] = None
    uncertainty: Optional[str] = None
    assumptions: Optional[str] = None

    @field_validator('severity')
    @classmethod
    def _validate_severity(cls, v: str) -> str:
        if v not in SEVERITY_LEVELS:
            raise ValueError(f"Invalid severity '{v}'")
        return v

    @field_validator('probability')
    @classmethod
    def _validate_probability(cls, v: str) -> str:
        if v not in PROBABILITY_LEVELS:
            raise ValueError(f"Invalid probability '{v}'")
        return v

    @field_validator('acceptability')
    @classmethod
    def _validate_acceptability(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in RISK_ACCEPTABILITY:
            raise ValueError(f"Invalid acceptability '{v}'")
        return v


class ResidualRiskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_analysis_uuid: str = Field(..., min_length=1)
    residual_severity: str = Field(..., description="negligible|minor|moderate|critical|catastrophic")
    residual_probability: str = Field(..., description="improbable|unlikely|possible|likely|probable")
    residual_risk_level: Optional[str] = None
    acceptability: Optional[str] = None
    rationale: Optional[str] = None

    @field_validator('residual_severity')
    @classmethod
    def _validate_rsev(cls, v: str) -> str:
        if v not in SEVERITY_LEVELS:
            raise ValueError(f"Invalid severity '{v}'")
        return v

    @field_validator('residual_probability')
    @classmethod
    def _validate_rprob(cls, v: str) -> str:
        if v not in PROBABILITY_LEVELS:
            raise ValueError(f"Invalid probability '{v}'")
        return v


# ---------------------------------------------------------------------------
# Risk Control
# ---------------------------------------------------------------------------

class RiskControlPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    control_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    control_option: str = Field(..., description="design_by_safety|protective_measure|information_for_safety")
    implementation_status: str = Field(..., description="proposed|implemented|verified")
    owner: Optional[str] = None
    due_date: Optional[str] = None
    verification_required: bool = True

    @field_validator('control_option')
    @classmethod
    def _validate_ctrl_opt(cls, v: str) -> str:
        if v not in RISK_CONTROL_OPTIONS:
            raise ValueError(f"Invalid control option '{v}'")
        return v

    @field_validator('implementation_status')
    @classmethod
    def _validate_impl_status(cls, v: str) -> str:
        if v not in CONTROL_IMPLEMENTATION_STATUS:
            raise ValueError(f"Invalid implementation status '{v}'")
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
    conclusion: str = Field(..., description="favorable|unfavorable|inconclusive")

    @field_validator('conclusion')
    @classmethod
    def _validate_conclusion(cls, v: str) -> str:
        if v not in BENEFIT_RISK_CONCLUSION:
            raise ValueError(f"Invalid benefit-risk conclusion '{v}'")
        return v


# ---------------------------------------------------------------------------
# Overall Residual Risk
# ---------------------------------------------------------------------------

class OverallResidualRiskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_id: str = Field(..., min_length=1)
    conclusion: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    unresolved_risks: List[str] = []
    reviewer_notes: Optional[str] = None
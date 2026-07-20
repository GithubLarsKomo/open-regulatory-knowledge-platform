"""
Risk calculation and evaluation engine for ORKP.

Deterministic functions for risk level calculation, acceptability evaluation,
and residual risk comparison.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from orkp.domain.risk_policy import RiskPolicy, default_risk_policy


def calculate_risk_level(
    severity: str,
    probability: str,
    policy: Optional[RiskPolicy] = None,
) -> Dict[str, Any]:
    """Calculate risk level from severity and probability.

    Returns structured RiskEvaluationResult.
    """
    if policy is None:
        policy = default_risk_policy()

    risk_level = policy.calculate_risk_level(severity, probability)
    acceptable = policy.is_acceptable(risk_level)
    action_required = 'none' if acceptable else 'controls_required'

    return {
        "severity": severity,
        "probability": probability,
        "risk_level": risk_level,
        "acceptable": acceptable,
        "action_required": action_required,
        "policy_version": policy.version,
        "warnings": [],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def compare_initial_and_residual_risk(
    initial_severity: str,
    initial_probability: str,
    residual_severity: str,
    residual_probability: str,
    policy: Optional[RiskPolicy] = None,
) -> Dict[str, Any]:
    """Compare initial and residual risk estimates.

    Returns ResidualRiskComparison.
    """
    if policy is None:
        policy = default_risk_policy()

    initial = calculate_risk_level(initial_severity, initial_probability, policy)
    residual = calculate_risk_level(residual_severity, residual_probability, policy)

    reduced = (
        policy.get_severity_index(residual_severity) < policy.get_severity_index(initial_severity)
        or policy.get_probability_index(residual_probability) < policy.get_probability_index(initial_probability)
    )

    benefit_risk_required = (
        not residual['acceptable']
        and policy.benefit_risk_required_for_unacceptable
    )

    return {
        "initial_risk": initial,
        "residual_risk": residual,
        "reduced": reduced,
        "acceptable": residual['acceptable'],
        "benefit_risk_required": benefit_risk_required,
        "warnings": [],
    }


def evaluate_control_effectiveness(
    control_status: str,
    verification_required: bool,
    has_approved_verification: bool,
) -> Dict[str, Any]:
    """Evaluate whether a risk control is effective.

    Returns structured assessment.
    """
    issues: List[str] = []
    effective = False

    if control_status == 'proposed':
        issues.append("Control is only proposed, not implemented")
    elif control_status == 'implemented':
        if verification_required and not has_approved_verification:
            issues.append("Control requires verification but no approved evidence")
        else:
            effective = True
    elif control_status == 'verified':
        if verification_required and not has_approved_verification:
            issues.append("Control status is 'verified' but no approved verification evidence found")
        else:
            effective = True

    return {
        "effective": effective,
        "control_status": control_status,
        "verification_required": verification_required,
        "has_approved_verification": has_approved_verification,
        "issues": issues,
    }
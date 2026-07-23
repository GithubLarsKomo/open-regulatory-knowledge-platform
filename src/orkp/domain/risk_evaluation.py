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
    action_required = "none" if acceptable else "controls_required"

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

    Returns ResidualRiskComparison with correct improvement/worsening detection.
    """
    if policy is None:
        policy = default_risk_policy()

    initial = calculate_risk_level(initial_severity, initial_probability, policy)
    residual = calculate_risk_level(residual_severity, residual_probability, policy)

    sv_i = policy.get_severity_index(initial_severity)
    sv_r = policy.get_severity_index(residual_severity)
    pb_i = policy.get_probability_index(initial_probability)
    pb_r = policy.get_probability_index(residual_probability)

    severity_improved = sv_r < sv_i
    severity_worsened = sv_r > sv_i
    probability_improved = pb_r < pb_i
    probability_worsened = pb_r > pb_i

    # Reduced only if neither worsened AND at least one improved
    reduced = (not severity_worsened and not probability_worsened) and (
        severity_improved or probability_improved
    )

    # Risk level comparison
    rl_order = {"low": 0, "medium": 1, "high": 2, "intolerable": 3}
    rl_i = rl_order.get(initial["risk_level"], 99)
    rl_r = rl_order.get(residual["risk_level"], 99)
    risk_level_improved = rl_r < rl_i
    regression_detected = severity_worsened or probability_worsened or rl_r > rl_i

    benefit_risk_required = not residual["acceptable"] and (
        policy.is_benefit_risk_required(initial["risk_level"])
        or policy.is_benefit_risk_required(residual["risk_level"])
    )

    return {
        "initial_risk": initial,
        "residual_risk": residual,
        "severity_improved": severity_improved,
        "probability_improved": probability_improved,
        "severity_worsened": severity_worsened,
        "probability_worsened": probability_worsened,
        "risk_level_improved": risk_level_improved,
        "reduced": reduced,
        "regression_detected": regression_detected,
        "acceptable": residual["acceptable"],
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

    if control_status == "proposed":
        issues.append("Control is only proposed, not implemented")
    elif control_status == "implemented":
        if verification_required and not has_approved_verification:
            issues.append("Control requires verification but no approved evidence")
        else:
            effective = True
    elif control_status == "verified":
        if verification_required and not has_approved_verification:
            issues.append(
                "Control status is 'verified' but no approved verification evidence found"
            )
        else:
            effective = True

    return {
        "effective": effective,
        "control_status": control_status,
        "verification_required": verification_required,
        "has_approved_verification": has_approved_verification,
        "issues": issues,
    }

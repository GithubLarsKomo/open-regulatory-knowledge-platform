"""
Risk completeness and approval gate for ORKP.

A Risk Analysis may only be approved when all traceability requirements
from Hazard to verification are met.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def evaluate_risk_completeness(
    risk_analysis_uuid: str,
    has_hazard: bool,
    has_sequence: bool,
    has_situation: bool,
    has_harm: bool,
    has_product: bool,
    has_controls: bool,
    controls_verified: bool,
    residual_evaluated: bool,
    residual_acceptable: bool,
    benefit_risk_approved: bool,
) -> Dict[str, Any]:
    """Evaluate whether a Risk Analysis is complete enough for approval.

    Never defaults missing evaluation to acceptable.
    Returns RiskCompletenessAssessment with detailed blocking issues.
    """
    issues: List[str] = []
    warnings: List[str] = []
    missing_objects: List[str] = []
    missing_relations: List[str] = []
    unverified_controls: List[str] = []
    unacceptable_residual: List[str] = []
    score = 0
    total_checks = 0

    checks = [
        (has_hazard, "No hazard linked", "hazard", "RISK-CHAIN-HAZARD-001"),
        (has_sequence, "No sequence of events linked", "sequence_of_events", "RISK-CHAIN-SEQUENCE-001"),
        (has_situation, "No hazardous situation linked", "hazardous_situation", "RISK-CHAIN-SITUATION-001"),
        (has_harm, "No harm linked", "harm", "RISK-CHAIN-HARM-001"),
        (has_product, "No product/device relation", "product_relation", "RISK-PRODUCT-LINK-001"),
        (has_controls, "No risk controls linked", "risk_controls", "RISK-CONTROL-MISSING-001"),
        (controls_verified, "Not all required controls have approved verification", "verification", "RISK-CONTROL-VERIFICATION-MISSING-001"),
        (residual_evaluated, "Residual risk not evaluated", "residual_evaluation", "RISK-EVAL-RESIDUAL-MISSING-001"),
    ]

    for passed, issue, obj_name, rule_code in checks:
        total_checks += 1
        if passed:
            score += 1
        else:
            issues.append(f"[{rule_code}] {issue}")
            if obj_name not in ('verification', 'residual_evaluation'):
                missing_objects.append(obj_name)
            elif obj_name == 'verification':
                unverified_controls.append("Controls lack approved verification")
            elif obj_name == 'residual_evaluation':
                unacceptable_residual.append("Residual risk not evaluated")

    # If residual is evaluated but unacceptable — require benefit-risk
    if residual_evaluated and not residual_acceptable:
        if benefit_risk_approved:
            warnings.append("[RISK-BENEFIT-001] Residual risk unacceptable but Benefit-Risk analysis approved")
            score += 1
        else:
            issues.append("[RISK-BENEFIT-001] Unacceptable residual risk requires approved Benefit-Risk analysis")
            unacceptable_residual.append("No approved Benefit-Risk analysis for unacceptable residual risk")
    elif not residual_evaluated:
        # Already handled above
        pass

    total_checks += 1
    if residual_acceptable or (not residual_acceptable and benefit_risk_approved):
        pass

    score = int((score / max(total_checks, 1)) * 100) if total_checks > 0 else 0

    if residual_evaluated and not residual_acceptable:
        if benefit_risk_approved:
            warnings.append("Residual risk unacceptable but Benefit-Risk analysis approved")
            score += 1
        else:
            issues.append("Unacceptable residual risk requires approved Benefit-Risk analysis")
            unacceptable_residual.append("No approved Benefit-Risk analysis for unacceptable residual risk")

    total_checks += 1
    if residual_acceptable or (not residual_acceptable and benefit_risk_approved):
        pass

    score = int((score / max(total_checks, 1)) * 100) if total_checks > 0 else 0

    return {
        "risk_analysis_uuid": risk_analysis_uuid,
        "complete": len(issues) == 0,
        "score": score,
        "blocking_issues": issues,
        "warnings": warnings,
        "missing_objects": missing_objects,
        "missing_relations": missing_relations,
        "unverified_controls": unverified_controls,
        "unacceptable_residual_risks": unacceptable_residual,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
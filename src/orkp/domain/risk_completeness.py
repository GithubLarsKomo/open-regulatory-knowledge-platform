"""Risk completeness and approval gate for ORKP.

A Risk Analysis may only be approved when all traceability requirements
from Hazard to verification are met.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List


def evaluate_risk_completeness(
    risk_analysis_uuid: str,
    has_hazard: bool,
    has_sequence: bool,
    has_situation: bool,
    has_harm: bool,
    has_estimation: bool,
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

    relation_names = {
        "hazard": "has_hazard",
        "sequence_of_events": "followed_by",
        "hazardous_situation": "creates_situation",
        "harm": "may_cause",
        "risk_estimation_relation": "estimated_for",
        "product_relation": "applies_to_product_or_device",
        "risk_controls": "controlled_by",
    }
    relation_only = {"risk_estimation_relation", "product_relation"}

    checks = [
        (has_hazard, "No current hazard linked", "hazard", "RISK-CHAIN-HAZARD-001"),
        (
            has_sequence,
            "Not every linked hazard has a current sequence of events",
            "sequence_of_events",
            "RISK-CHAIN-SEQUENCE-001",
        ),
        (
            has_situation,
            "Not every current sequence reaches a hazardous situation",
            "hazardous_situation",
            "RISK-CHAIN-SITUATION-001",
        ),
        (
            has_harm,
            "Not every current hazardous situation is linked to harm",
            "harm",
            "RISK-CHAIN-HARM-001",
        ),
        (
            has_estimation,
            "Not every current hazardous situation is estimated by the Risk Analysis",
            "risk_estimation_relation",
            "RISK-CHAIN-ESTIMATION-001",
        ),
        (
            has_product,
            "No product/device relation",
            "product_relation",
            "RISK-PRODUCT-LINK-001",
        ),
        (
            has_controls,
            "No risk controls linked",
            "risk_controls",
            "RISK-CONTROL-MISSING-001",
        ),
        (
            controls_verified,
            "Not all required controls have approved verification",
            "verification",
            "RISK-CONTROL-VERIFICATION-MISSING-001",
        ),
        (
            residual_evaluated,
            "Residual risk not evaluated",
            "residual_evaluation",
            "RISK-EVAL-RESIDUAL-MISSING-001",
        ),
    ]

    for passed, issue, obj_name, rule_code in checks:
        total_checks += 1
        if passed:
            score += 1
        else:
            issues.append(f"[{rule_code}] {issue}")
            relation_name = relation_names.get(obj_name)
            if relation_name is not None:
                missing_relations.append(relation_name)
            if obj_name not in (
                "verification",
                "residual_evaluation",
                *relation_only,
            ):
                missing_objects.append(obj_name)
            elif obj_name == "verification":
                unverified_controls.append("Controls lack approved verification")
            elif obj_name == "residual_evaluation":
                unacceptable_residual.append("Residual risk not evaluated")

    # Residual disposition is a distinct approval gate. An unacceptable
    # residual risk is complete only when an approved favorable Benefit-Risk
    # Analysis exists.
    total_checks += 1
    if residual_evaluated and residual_acceptable:
        score += 1
    elif residual_evaluated and benefit_risk_approved:
        score += 1
        warnings.append(
            "[RISK-BENEFIT-001] Residual risk unacceptable but Benefit-Risk analysis approved"
        )
    elif residual_evaluated:
        issues.append(
            "[RISK-BENEFIT-001] Unacceptable residual risk requires approved Benefit-Risk analysis"
        )
        unacceptable_residual.append(
            "No approved Benefit-Risk analysis for unacceptable residual risk"
        )

    score = int((score / max(total_checks, 1)) * 100)

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

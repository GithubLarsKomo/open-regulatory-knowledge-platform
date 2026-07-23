"""
Product completeness evaluator for ORKP.

Determines whether a product meets minimum requirements for approval.
"""

from typing import Any, Dict, List

from orkp.domain.models import ProductPayload


def evaluate_product_completeness(
    product_uuid: str,
    payload: ProductPayload,
    relations: Dict[str, List[Any]],
) -> Dict[str, Any]:
    """Evaluate product completeness and return a structured result.

    Args:
        product_uuid: The product UUID hex.
        payload: The validated ProductPayload.
        relations: Dict of relation types to lists of relation objects.

    Returns:
        Dict with complete, score, missing_required_fields,
        missing_relationships, and warnings.
    """
    missing_fields: List[str] = []
    missing_relationships: List[str] = []
    warnings: List[str] = []

    # Check required fields
    if not payload.product_id:
        missing_fields.append("product_id")
    if not payload.name:
        missing_fields.append("name")
    if not payload.legal_manufacturer:
        missing_fields.append("legal_manufacturer")
    if not payload.intended_purpose:
        missing_fields.append("intended_purpose")
    if not payload.regulatory_status:
        missing_fields.append("regulatory_status")

    # Check at least one applicable regulation for assay or kit
    if payload.product_kind in ("assay", "kit") and not payload.applicable_regulations:
        warnings.append("No applicable regulations defined for assay/kit product")

    # Check relationships
    has_claims = len(relations.get("has_claim", [])) > 0
    has_risks = len(relations.get("has_risk", [])) > 0

    if not has_claims:
        missing_relationships.append("at least one claim relation")
    if not has_risks:
        missing_relationships.append("at least one risk relation")

    # Score calculation
    total_checks = 5 + 2  # fields + relationships
    passed = 0
    if not any(f == "product_id" for f in missing_fields):
        passed += 1
    if not any(f == "name" for f in missing_fields):
        passed += 1
    if not any(f == "legal_manufacturer" for f in missing_fields):
        passed += 1
    if not any(f == "intended_purpose" for f in missing_fields):
        passed += 1
    if not any(f == "regulatory_status" for f in missing_fields):
        passed += 1
    if has_claims:
        passed += 1
    if has_risks:
        passed += 1

    score = int((passed / total_checks) * 100) if total_checks > 0 else 0

    # Minimum approval requirements
    complete = (
        payload.product_id
        and payload.name
        and payload.legal_manufacturer
        and payload.intended_purpose
        and payload.regulatory_status
        and has_claims
        and has_risks
    )

    return {
        "complete": complete,
        "score": score,
        "missing_required_fields": missing_fields,
        "missing_relationships": missing_relationships,
        "warnings": warnings,
    }

"""
Evidence coverage evaluation for ORKP.

Evaluates evidence sufficiency for claims and products.
"""

from typing import Any, Dict, List


def evaluate_evidence_coverage(
    claim_uuid: str,
    evidence_relations: List[Dict[str, Any]],
    evidence_objects: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Evaluate evidence coverage for a claim.

    Args:
        claim_uuid: Claim UUID hex.
        evidence_relations: List of relations targeting the claim.
        evidence_objects: Dict of evidence_uuid -> evidence payload/status.

    Returns:
        Dict with coverage score, missing information, quality warnings, etc.
    """
    total_relations = len(evidence_relations)
    approved_evidence = 0
    high_quality = 0
    quality_warnings: List[str] = []
    linked_evidence_uuids: List[str] = []

    for rel in evidence_relations:
        ev_uuid = rel.get("source_uuid_hex", "")
        linked_evidence_uuids.append(ev_uuid)
        ev = evidence_objects.get(ev_uuid)
        if ev and ev.get("lifecycle_state") == "approved":
            approved_evidence += 1
            if ev.get("quality_rating") == "high":
                high_quality += 1
            elif ev.get("quality_rating") == "low":
                quality_warnings.append(
                    f"Evidence {ev_uuid[:8]} has low quality rating"
                )

    coverage_score = 0
    if total_relations > 0:
        coverage_score = int((approved_evidence / total_relations) * 100)

    has_approved_evidence = approved_evidence > 0
    has_high_quality = high_quality > 0

    return {
        "claim_uuid": claim_uuid,
        "total_evidence_relations": total_relations,
        "approved_evidence_count": approved_evidence,
        "high_quality_count": high_quality,
        "coverage_score": coverage_score,
        "has_approved_evidence": has_approved_evidence,
        "has_high_quality_evidence": has_high_quality,
        "quality_warnings": quality_warnings,
        "linked_evidence_uuids": linked_evidence_uuids,
        "approval_ready": has_approved_evidence,
    }

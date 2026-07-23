"""
Claim consistency checker for ORKP.

Detects conflicting, duplicate or unsupported approved claims.
"""

from typing import Any, Dict, List


def check_claim_consistency(
    claims: List[Dict[str, Any]],
    evidence_map: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Check consistency across a set of claims.

    Args:
        claims: List of claim dicts with payload, uuid, lifecycle_state.
        evidence_map: Dict of claim_uuid -> list of evidence relations.

    Returns:
        Dict with conflicts, duplicates, unsupported, obsolete evidence.
    """
    conflicts: List[Dict[str, Any]] = []
    duplicates: List[Dict[str, Any]] = []
    unsupported: List[Dict[str, Any]] = []
    obsolete_evidence: List[Dict[str, Any]] = []

    # Check for duplicate wording among approved claims
    approved_claims = [c for c in claims if c.get("lifecycle_state") == "approved"]
    wording_map: Dict[str, List[str]] = {}
    for c in approved_claims:
        w = c.get("payload", {}).get("wording", "").lower().strip()
        if w not in wording_map:
            wording_map[w] = []
        wording_map[w].append(c.get("object_uuid", ""))

    for wording, uuids in wording_map.items():
        if len(uuids) > 1:
            duplicates.append(
                {
                    "wording": wording,
                    "claim_uuids": uuids,
                    "type": "duplicate_wording",
                }
            )

    # Check for unsupported claims (no evidence relations)
    for c in claims:
        cuuid = c.get("object_uuid", "")
        ev_list = evidence_map.get(cuuid, [])
        if not ev_list and c.get("lifecycle_state") == "approved":
            unsupported.append(
                {
                    "claim_uuid": cuuid,
                    "wording": c.get("payload", {}).get("wording", "")[:100],
                    "type": "unsupported_claim",
                }
            )

    # Check for contradictory claims
    for c in approved_claims:
        cuuid = c.get("object_uuid", "")
        ev_list = evidence_map.get(cuuid, [])
        for ev in ev_list:
            if ev.get("relation_type") == "contradicted_by":
                conflicts.append(
                    {
                        "claim_uuid": cuuid,
                        "evidence_uuid": ev.get("source_uuid_hex", ""),
                        "type": "contradicted_claim",
                    }
                )

    return {
        "total_claims_checked": len(claims),
        "approved_claims": len(approved_claims),
        "conflicts": conflicts,
        "duplicates": duplicates,
        "unsupported_claims": unsupported,
        "obsolete_evidence": obsolete_evidence,
        "consistent": len(conflicts) == 0
        and len(duplicates) == 0
        and len(unsupported) == 0,
    }

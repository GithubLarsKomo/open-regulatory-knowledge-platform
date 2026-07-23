"""
Centralized relation policy for ORKP.

Validates canonical source/target object types for every relation type.
"""

from dataclasses import dataclass
from typing import Dict, FrozenSet

from orkp.domain.exceptions import InvalidRelationError


@dataclass(frozen=True)
class RelationRule:
    """Canonical rule for a relation type."""

    source_types: FrozenSet[str]
    target_types: FrozenSet[str]


# Canonical relation schema
RELATION_SCHEMA: Dict[str, RelationRule] = {
    # Product
    "variant_of": RelationRule(
        source_types=frozenset({"device"}), target_types=frozenset({"product"})
    ),
    "has_claim": RelationRule(
        source_types=frozenset({"product"}), target_types=frozenset({"claim"})
    ),
    "has_risk": RelationRule(
        source_types=frozenset({"product"}), target_types=frozenset({"risk_analysis"})
    ),
    "has_evidence": RelationRule(
        source_types=frozenset({"product"}), target_types=frozenset({"evidence"})
    ),
    "supported_by": RelationRule(
        source_types=frozenset({"evidence"}), target_types=frozenset({"claim"})
    ),
    "contradicted_by": RelationRule(
        source_types=frozenset({"evidence"}), target_types=frozenset({"claim"})
    ),
    "supersedes": RelationRule(
        source_types=frozenset({"evidence"}), target_types=frozenset({"evidence"})
    ),
    "has_hazard": RelationRule(
        source_types=frozenset({"risk_analysis"}), target_types=frozenset({"hazard"})
    ),
    "followed_by": RelationRule(
        source_types=frozenset({"hazard"}),
        target_types=frozenset({"sequence_of_events"}),
    ),
    "creates_situation": RelationRule(
        source_types=frozenset({"sequence_of_events"}),
        target_types=frozenset({"hazardous_situation"}),
    ),
    "may_cause": RelationRule(
        source_types=frozenset({"hazardous_situation"}),
        target_types=frozenset({"harm"}),
    ),
    "estimated_for": RelationRule(
        source_types=frozenset({"risk_analysis"}),
        target_types=frozenset({"hazardous_situation"}),
    ),
    "controlled_by": RelationRule(
        source_types=frozenset({"risk_analysis"}),
        target_types=frozenset({"risk_control"}),
    ),
    "verifies_control": RelationRule(
        source_types=frozenset({"evidence"}), target_types=frozenset({"risk_control"})
    ),
    "supports_verification": RelationRule(
        source_types=frozenset({"evidence"}),
        target_types=frozenset({"control_verification"}),
    ),
    "evaluates_initial_risk_of": RelationRule(
        source_types=frozenset({"initial_risk_evaluation"}),
        target_types=frozenset({"risk_analysis"}),
    ),
    "uses_risk_policy": RelationRule(
        source_types=frozenset({"initial_risk_evaluation", "residual_risk_evaluation"}),
        target_types=frozenset({"risk_policy"}),
    ),
    "residual_of": RelationRule(
        source_types=frozenset({"residual_risk_evaluation"}),
        target_types=frozenset({"risk_analysis"}),
    ),
    "derived_from_initial_evaluation": RelationRule(
        source_types=frozenset({"residual_risk_evaluation"}),
        target_types=frozenset({"initial_risk_evaluation"}),
    ),
    "benefit_risk_for": RelationRule(
        source_types=frozenset({"benefit_risk"}),
        target_types=frozenset({"residual_risk_evaluation"}),
    ),
    "applies_to_product": RelationRule(
        source_types=frozenset({"risk_analysis"}), target_types=frozenset({"product"})
    ),
    "applies_to_device": RelationRule(
        source_types=frozenset({"risk_analysis"}), target_types=frozenset({"device"})
    ),
    "overall_risk_for": RelationRule(
        source_types=frozenset({"overall_residual_risk"}),
        target_types=frozenset({"product"}),
    ),
    "governed_by": RelationRule(
        source_types=frozenset({"product"}), target_types=frozenset({"regulation"})
    ),
    "manufactured_by": RelationRule(
        source_types=frozenset({"product"}), target_types=frozenset({"organization"})
    ),
    "approved_by": RelationRule(
        source_types=frozenset({"risk_analysis"}), target_types=frozenset({"user"})
    ),
    "marketed_in": RelationRule(
        source_types=frozenset({"product"}), target_types=frozenset({"jurisdiction"})
    ),
    "references": RelationRule(
        source_types=frozenset({"claim"}), target_types=frozenset({"standard"})
    ),
    "derived_from": RelationRule(
        source_types=frozenset({"claim"}), target_types=frozenset({"study"})
    ),
    "generated_from": RelationRule(
        source_types=frozenset({"report"}), target_types=frozenset({"claim"})
    ),
    "included_in": RelationRule(
        source_types=frozenset({"section"}), target_types=frozenset({"report"})
    ),
    "impacts": RelationRule(
        source_types=frozenset({"change"}), target_types=frozenset({"risk_analysis"})
    ),
    "informed_by": RelationRule(
        source_types=frozenset({"risk_analysis"}),
        target_types=frozenset({"post_market_information"}),
    ),
    "impacts_risk": RelationRule(
        source_types=frozenset({"post_market_information"}),
        target_types=frozenset({"risk_analysis"}),
    ),
    "requires_review": RelationRule(
        source_types=frozenset({"finding"}), target_types=frozenset({"risk_analysis"})
    ),
}


def validate_relation(
    source_object_type: str, relation_type: str, target_object_type: str
) -> None:
    """Validate that a relation between source and target types is canonical.

    Raises InvalidRelationError if the relation is not defined or types mismatch.
    """
    rule = RELATION_SCHEMA.get(relation_type)
    if rule is None:
        raise InvalidRelationError(f"Unknown relation type '{relation_type}'")
    if source_object_type not in rule.source_types:
        raise InvalidRelationError(
            f"Relation '{relation_type}' requires source type in {rule.source_types}, got '{source_object_type}'"
        )
    if target_object_type not in rule.target_types:
        raise InvalidRelationError(
            f"Relation '{relation_type}' requires target type in {rule.target_types}, got '{target_object_type}'"
        )

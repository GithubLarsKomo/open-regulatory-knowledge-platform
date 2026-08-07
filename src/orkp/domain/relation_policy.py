"""Centralized canonical relation policy for ORKP."""

from dataclasses import dataclass
from typing import Dict, FrozenSet

from orkp.domain.exceptions import InvalidRelationError


@dataclass(frozen=True)
class RelationRule:
    source_types: FrozenSet[str]
    target_types: FrozenSet[str]


RELATION_SCHEMA: Dict[str, RelationRule] = {
    "variant_of": RelationRule(frozenset({"device"}), frozenset({"product"})),
    "has_claim": RelationRule(frozenset({"product"}), frozenset({"claim"})),
    "has_risk": RelationRule(frozenset({"product"}), frozenset({"risk_analysis"})),
    "has_evidence": RelationRule(frozenset({"product"}), frozenset({"evidence"})),
    "supported_by": RelationRule(frozenset({"evidence"}), frozenset({"claim"})),
    "contradicted_by": RelationRule(frozenset({"evidence"}), frozenset({"claim"})),
    "supersedes": RelationRule(
        frozenset({"evidence", "control_verification"}),
        frozenset({"evidence", "control_verification"}),
    ),
    "has_hazard": RelationRule(frozenset({"risk_analysis"}), frozenset({"hazard"})),
    "followed_by": RelationRule(
        frozenset({"hazard"}), frozenset({"sequence_of_events"})
    ),
    "creates_situation": RelationRule(
        frozenset({"sequence_of_events"}), frozenset({"hazardous_situation"})
    ),
    "may_cause": RelationRule(frozenset({"hazardous_situation"}), frozenset({"harm"})),
    "estimated_for": RelationRule(
        frozenset({"risk_analysis"}), frozenset({"hazardous_situation"})
    ),
    "controlled_by": RelationRule(
        frozenset({"risk_analysis"}), frozenset({"risk_control"})
    ),
    "implements_requirement": RelationRule(
        frozenset({"risk_control"}), frozenset({"requirement"})
    ),
    "verifies_control": RelationRule(
        frozenset({"evidence", "control_verification"}),
        frozenset({"risk_control"}),
    ),
    "supports_verification": RelationRule(
        frozenset({"evidence"}), frozenset({"control_verification"})
    ),
    "evaluates_initial_risk_of": RelationRule(
        frozenset({"initial_risk_evaluation"}), frozenset({"risk_analysis"})
    ),
    "uses_risk_policy": RelationRule(
        frozenset(
            {
                "initial_risk_evaluation",
                "residual_risk_evaluation",
                "control_verification",
                "benefit_risk",
                "overall_residual_risk",
            }
        ),
        frozenset({"risk_policy"}),
    ),
    "residual_of": RelationRule(
        frozenset({"residual_risk_evaluation"}), frozenset({"risk_analysis"})
    ),
    "derived_from_initial_evaluation": RelationRule(
        frozenset({"residual_risk_evaluation", "control_verification"}),
        frozenset({"initial_risk_evaluation"}),
    ),
    "benefit_risk_for": RelationRule(
        frozenset({"benefit_risk"}), frozenset({"residual_risk_evaluation"})
    ),
    "applies_to_product": RelationRule(
        frozenset({"risk_analysis"}), frozenset({"product"})
    ),
    "applies_to_device": RelationRule(
        frozenset({"risk_analysis"}), frozenset({"device"})
    ),
    "overall_risk_for": RelationRule(
        frozenset({"overall_residual_risk"}), frozenset({"product"})
    ),
    "aggregates_residual_risk": RelationRule(
        frozenset({"overall_residual_risk"}),
        frozenset({"residual_risk_evaluation"}),
    ),
    "considers_benefit_risk": RelationRule(
        frozenset({"overall_residual_risk"}), frozenset({"benefit_risk"})
    ),
    "governed_by": RelationRule(frozenset({"product"}), frozenset({"regulation"})),
    "manufactured_by": RelationRule(
        frozenset({"product"}), frozenset({"organization"})
    ),
    "approved_by": RelationRule(frozenset({"risk_analysis"}), frozenset({"user"})),
    "marketed_in": RelationRule(frozenset({"product"}), frozenset({"jurisdiction"})),
    "references": RelationRule(frozenset({"claim"}), frozenset({"standard"})),
    "derived_from": RelationRule(
        frozenset(
            {
                "claim",
                "control_verification",
                "evidence",
                "residual_risk_evaluation",
                "risk_impact_assessment",
            }
        ),
        frozenset(
            {
                "study",
                "risk_analysis",
                "control_verification",
                "evidence",
                "post_market_information",
            }
        ),
    ),
    "generated_from": RelationRule(frozenset({"report"}), frozenset({"claim"})),
    "included_in": RelationRule(frozenset({"section"}), frozenset({"report"})),
    "impacts": RelationRule(frozenset({"change"}), frozenset({"risk_analysis"})),
    "informed_by": RelationRule(
        frozenset({"risk_analysis"}), frozenset({"post_market_information"})
    ),
    "impacts_risk": RelationRule(
        frozenset({"post_market_information"}), frozenset({"risk_analysis"})
    ),
    "requires_review": RelationRule(
        frozenset({"finding"}), frozenset({"risk_analysis"})
    ),
}


def validate_relation(
    source_object_type: str, relation_type: str, target_object_type: str
) -> None:
    rule = RELATION_SCHEMA.get(relation_type)
    if rule is None:
        raise InvalidRelationError(f"Unknown relation type '{relation_type}'")
    if source_object_type not in rule.source_types:
        raise InvalidRelationError(
            f"Relation '{relation_type}' requires source type in {rule.source_types}, "
            f"got '{source_object_type}'"
        )
    if target_object_type not in rule.target_types:
        raise InvalidRelationError(
            f"Relation '{relation_type}' requires target type in {rule.target_types}, "
            f"got '{target_object_type}'"
        )

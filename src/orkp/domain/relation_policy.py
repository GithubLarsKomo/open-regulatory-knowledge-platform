"""
Centralized relation policy for ORKP.

Validates canonical source/target object types for every relation type.
"""

from typing import Dict, List, Optional, Tuple

from orkp.domain.exceptions import InvalidRelationError


# Canonical relation schema: relation_type -> (source_object_type, target_object_type)
RELATION_SCHEMA: Dict[str, Tuple[str, str]] = {
    # Product
    'variant_of': ('device', 'product'),
    'has_claim': ('product', 'claim'),
    'has_risk': ('product', 'risk_analysis'),
    'has_evidence': ('product', 'evidence'),
    # Claim/Evidence
    'supported_by': ('evidence', 'claim'),
    'contradicted_by': ('evidence', 'claim'),
    'supersedes': ('evidence', 'evidence'),
    # Risk chain
    'has_hazard': ('risk_analysis', 'hazard'),
    'followed_by': ('hazard', 'sequence_of_events'),
    'creates_situation': ('sequence_of_events', 'hazardous_situation'),
    'may_cause': ('hazardous_situation', 'harm'),
    'estimated_for': ('risk_analysis', 'hazardous_situation'),
    'controlled_by': ('risk_analysis', 'risk_control'),
    'verifies_control': ('evidence', 'risk_control'),
    'supports_verification': ('evidence', 'control_verification'),
    # Evaluations — uses_risk_policy accepts multiple source types
    'evaluates_initial_risk_of': ('initial_risk_evaluation', 'risk_analysis'),
    'uses_risk_policy': (('initial_risk_evaluation', 'residual_risk_evaluation'), 'risk_policy'),
    'residual_of': ('residual_risk_evaluation', 'risk_analysis'),
    'derived_from_initial_evaluation': ('residual_risk_evaluation', 'initial_risk_evaluation'),
    # Benefit-Risk
    'benefit_risk_for': ('benefit_risk', 'residual_risk_evaluation'),
    # Product/Device links
    'applies_to_product': ('risk_analysis', 'product'),
    'applies_to_device': ('risk_analysis', 'device'),
    'overall_risk_for': ('overall_residual_risk', 'product'),
    # Other
    'governed_by': ('product', 'regulation'),
    'manufactured_by': ('product', 'organization'),
    'approved_by': ('risk_analysis', 'user'),
    'marketed_in': ('product', 'jurisdiction'),
    'references': ('claim', 'standard'),
    'derived_from': ('claim', 'study'),
    'generated_from': ('report', 'claim'),
    'included_in': ('section', 'report'),
    'impacts': ('change', 'risk_analysis'),
    'informed_by': ('risk_analysis', 'post_market_information'),
    'impacts_risk': ('post_market_information', 'risk_analysis'),
    'requires_review': ('finding', 'risk_analysis'),
}


def validate_relation(source_object_type: str, relation_type: str, target_object_type: str) -> None:
    """Validate that a relation between source and target types is canonical.

    Raises InvalidRelationError if the relation is not defined or types mismatch.
    """
    schema = RELATION_SCHEMA.get(relation_type)
    if schema is None:
        raise InvalidRelationError(f"Unknown relation type '{relation_type}'")
    expected_src, expected_tgt = schema
    # Allow multiple source types for polymorphic relations
    allowed_sources = expected_src if isinstance(expected_src, tuple) else (expected_src,)
    if source_object_type not in allowed_sources:
        raise InvalidRelationError(
            f"Relation '{relation_type}' requires source type one of {allowed_sources}, got '{source_object_type}'"
        )
    if target_object_type != expected_tgt:
        raise InvalidRelationError(
            f"Relation '{relation_type}' requires target type '{expected_tgt}', got '{target_object_type}'"
        )
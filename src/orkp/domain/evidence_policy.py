"""
Configurable evidence quality policy for ORKP.

Defines minimum quality requirements for evidence used in claim approval.
Supports jurisdiction-specific policies and dependency injection for testing.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class EvidencePolicy:
    """Configurable evidence quality policy."""

    minimum_quality_for_approval: str = 'medium'
    high_severity_requires_high_quality: bool = True
    marketing_claims_require_product_relation: bool = True

    allowed_evidence_types: Dict[str, List[str]] = field(default_factory=lambda: {
        'clinical': ['literature', 'clinical_study', 'scientific_validity'],
        'analytical': ['analytical_study', 'internal_report'],
        'performance': ['analytical_study', 'clinical_study', 'literature'],
        'regulatory': ['regulation', 'guideline', 'literature'],
        'safety': ['literature', 'clinical_study', 'internal_report'],
        'marketing': ['literature', 'clinical_study', 'standard'],
        'manufacturing': ['internal_report', 'standard', 'regulation'],
        'software': ['literature', 'standard', 'internal_report'],
    })

    def get_min_quality_for_severity(self, severity: str) -> str:
        """Get minimum quality rating for a claim severity level."""
        if severity == 'high' and self.high_severity_requires_high_quality:
            return 'high'
        return self.minimum_quality_for_approval

    def get_allowed_evidence_types(self, claim_type: str) -> List[str]:
        """Get allowed evidence types for a claim type."""
        return self.allowed_evidence_types.get(claim_type, ['literature', 'clinical_study'])


def default_evidence_policy() -> EvidencePolicy:
    """Return the default evidence policy."""
    return EvidencePolicy()
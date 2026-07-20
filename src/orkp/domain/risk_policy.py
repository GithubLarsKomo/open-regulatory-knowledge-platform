"""
Configurable risk policy for ORKP.

Defines severity/probability scales, risk matrix, acceptability thresholds,
control hierarchy and rules for Benefit-Risk and Overall Residual Risk.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class RiskPolicy:
    """Configurable risk management policy."""

    severity_scale: List[str] = field(default_factory=lambda:
        ['negligible', 'minor', 'moderate', 'critical', 'catastrophic'])
    probability_scale: List[str] = field(default_factory=lambda:
        ['improbable', 'unlikely', 'possible', 'likely', 'probable'])

    # Risk matrix: severity -> probability -> risk_level
    # Default is ISO 14971-like
    risk_matrix: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        'catastrophic': {'improbable': 'high', 'unlikely': 'high', 'possible': 'intolerable', 'likely': 'intolerable', 'probable': 'intolerable'},
        'critical': {'improbable': 'medium', 'unlikely': 'high', 'possible': 'high', 'likely': 'intolerable', 'probable': 'intolerable'},
        'moderate': {'improbable': 'medium', 'unlikely': 'medium', 'possible': 'high', 'likely': 'high', 'probable': 'intolerable'},
        'minor': {'improbable': 'low', 'unlikely': 'medium', 'possible': 'medium', 'likely': 'high', 'probable': 'high'},
        'negligible': {'improbable': 'low', 'unlikely': 'low', 'possible': 'medium', 'likely': 'medium', 'probable': 'high'},
    })

    # Acceptability rules: risk_level -> acceptable bool
    acceptability_rules: Dict[str, bool] = field(default_factory=lambda: {
        'low': True,
        'medium': True,
        'high': False,
        'intolerable': False,
    })

    # Control hierarchy (ISO 14971: design safety > protective > information)
    control_hierarchy: List[str] = field(default_factory=lambda:
        ['design_by_safety', 'protective_measure', 'information_for_safety'])

    # Whether Benefit-Risk is required for unacceptable residual risk
    benefit_risk_required_for_unacceptable: bool = True

    # Policy version identifier
    version: str = '1.0'

    def get_severity_index(self, severity: str) -> int:
        if severity not in self.severity_scale:
            raise ValueError(f"Unknown severity '{severity}'")
        return self.severity_scale.index(severity)

    def get_probability_index(self, probability: str) -> int:
        if probability not in self.probability_scale:
            raise ValueError(f"Unknown probability '{probability}'")
        return self.probability_scale.index(probability)

    def calculate_risk_level(self, severity: str, probability: str) -> str:
        """Calculate risk level from severity and probability."""
        s_row = self.risk_matrix.get(severity)
        if s_row is None:
            raise ValueError(f"Unknown severity '{severity}'")
        risk = s_row.get(probability)
        if risk is None:
            raise ValueError(f"Unknown probability '{probability}' for severity '{severity}'")
        return risk

    def is_acceptable(self, risk_level: str) -> bool:
        """Check if risk level is acceptable."""
        return self.acceptability_rules.get(risk_level, False)

    def validate(self) -> List[str]:
        """Validate policy completeness and consistency. Returns list of issues."""
        issues = []
        levels = {'low', 'medium', 'high', 'intolerable'}
        for sev in self.severity_scale:
            row = self.risk_matrix.get(sev)
            if row is None:
                issues.append(f"Missing row for severity '{sev}'")
                continue
            for prob in self.probability_scale:
                val = row.get(prob)
                if val is None:
                    issues.append(f"Missing cell for {sev}/{prob}")
                elif val not in levels:
                    issues.append(f"Invalid risk level '{val}' at {sev}/{prob}")
        return issues


def default_risk_policy() -> RiskPolicy:
    """Return the default risk policy."""
    return RiskPolicy()
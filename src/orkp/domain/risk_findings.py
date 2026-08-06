"""Stable rule codes and severities for Risk review findings."""

from typing import Literal, TypedDict

RiskFindingSeverity = Literal["error", "warning"]


class RiskFinding(TypedDict):
    """Machine-readable Risk review finding."""

    rule_code: str
    severity: RiskFindingSeverity
    message: str
    blocking: bool


RISK_FINDING_SEVERITIES: dict[str, RiskFindingSeverity] = {
    "RISK-CHAIN-HAZARD-001": "error",
    "RISK-CHAIN-SEQUENCE-001": "error",
    "RISK-CHAIN-SITUATION-001": "error",
    "RISK-CHAIN-HARM-001": "error",
    "RISK-CHAIN-ESTIMATION-001": "error",
    "RISK-PRODUCT-LINK-001": "error",
    "RISK-CONTROL-MISSING-001": "error",
    "RISK-CONTROL-VERIFICATION-MISSING-001": "error",
    "RISK-EVAL-RESIDUAL-MISSING-001": "error",
    "RISK-BENEFIT-001": "error",
    "RISK-BENEFIT-ACCEPTED-001": "warning",
}


def make_risk_finding(rule_code: str, message: str) -> RiskFinding:
    """Create a finding from the canonical rule/severity catalog."""
    severity = RISK_FINDING_SEVERITIES[rule_code]
    return {
        "rule_code": rule_code,
        "severity": severity,
        "message": message,
        "blocking": severity == "error",
    }

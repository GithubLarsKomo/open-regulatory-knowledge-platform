"""Regression tests for stable Risk review rule codes and severities."""

from orkp.domain.risk_completeness import evaluate_risk_completeness
from orkp.domain.risk_findings import RISK_FINDING_SEVERITIES


def _evaluate(**overrides):
    values = {
        "risk_analysis_uuid": "a" * 32,
        "has_hazard": True,
        "has_sequence": True,
        "has_situation": True,
        "has_harm": True,
        "has_estimation": True,
        "has_product": True,
        "has_controls": True,
        "controls_verified": True,
        "residual_evaluated": True,
        "residual_acceptable": True,
        "benefit_risk_approved": False,
    }
    values.update(overrides)
    return evaluate_risk_completeness(**values)


def _legacy_code(text: str) -> str:
    return text.split("]", 1)[0].removeprefix("[")


def test_every_blocking_issue_has_matching_error_finding():
    result = _evaluate(
        has_hazard=False,
        has_sequence=False,
        has_situation=False,
        has_harm=False,
        has_estimation=False,
        has_product=False,
        has_controls=False,
        controls_verified=False,
        residual_evaluated=False,
    )

    finding_by_code = {finding["rule_code"]: finding for finding in result["findings"]}
    blocker_codes = {_legacy_code(issue) for issue in result["blocking_issues"]}

    assert blocker_codes
    assert blocker_codes <= set(finding_by_code)
    assert all(finding_by_code[code]["severity"] == "error" for code in blocker_codes)
    assert all(finding_by_code[code]["blocking"] is True for code in blocker_codes)


def test_unacceptable_residual_without_benefit_risk_is_error():
    result = _evaluate(residual_acceptable=False, benefit_risk_approved=False)

    finding = next(
        finding
        for finding in result["findings"]
        if finding["rule_code"] == "RISK-BENEFIT-001"
    )

    assert result["complete"] is False
    assert finding["severity"] == "error"
    assert finding["blocking"] is True


def test_favorable_benefit_risk_uses_distinct_warning_finding():
    result = _evaluate(residual_acceptable=False, benefit_risk_approved=True)

    finding = next(
        finding
        for finding in result["findings"]
        if finding["rule_code"] == "RISK-BENEFIT-ACCEPTED-001"
    )

    assert result["complete"] is True
    assert finding["severity"] == "warning"
    assert finding["blocking"] is False
    assert any("RISK-BENEFIT-001" in warning for warning in result["warnings"])


def test_acceptable_complete_risk_has_no_findings():
    result = _evaluate()

    assert result["complete"] is True
    assert result["findings"] == []
    assert result["blocking_issues"] == []
    assert result["warnings"] == []


def test_finding_catalog_uses_only_stable_supported_severities():
    assert set(RISK_FINDING_SEVERITIES.values()) <= {"error", "warning"}
    assert RISK_FINDING_SEVERITIES["RISK-BENEFIT-001"] == "error"
    assert RISK_FINDING_SEVERITIES["RISK-BENEFIT-ACCEPTED-001"] == "warning"

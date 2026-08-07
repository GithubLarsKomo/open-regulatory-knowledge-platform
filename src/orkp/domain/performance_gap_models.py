"""Strict models for Product-scoped Performance Claim evidence gaps."""

from pydantic import BaseModel, ConfigDict, field_validator

from orkp.domain.risk_models import VersionedObjectReference


PERFORMANCE_CLAIM_TYPES = {"clinical", "analytical", "performance"}
PERFORMANCE_GAP_CODES = {
    "PERF-EVID-MISSING-001",
    "PERF-EVID-UNAPPROVED-001",
    "PERF-EVID-QUALITY-001",
    "PERF-EVID-TYPE-001",
    "PERF-EVID-CONTRADICTION-001",
    "PERF-CLAIM-LINK-STALE-001",
}


class PerformanceClaimGapFinding(BaseModel):
    """One stable machine-readable Performance evidence gap."""

    model_config = ConfigDict(extra="forbid")

    rule_code: str
    message: str
    evidence: VersionedObjectReference | None = None

    @field_validator("rule_code")
    @classmethod
    def validate_rule_code(cls, value: str) -> str:
        if value not in PERFORMANCE_GAP_CODES:
            raise ValueError(f"Unknown Performance gap rule_code '{value}'")
        return value


class PerformanceClaimGapItem(BaseModel):
    """Evidence sufficiency result for one current Performance-relevant Claim."""

    model_config = ConfigDict(extra="forbid")

    claim: VersionedObjectReference
    claim_type: str
    wording: str
    sufficient: bool
    supporting_evidence_count: int
    findings: list[PerformanceClaimGapFinding]

    @field_validator("claim_type")
    @classmethod
    def validate_claim_type(cls, value: str) -> str:
        if value not in PERFORMANCE_CLAIM_TYPES:
            raise ValueError(f"Invalid Performance claim_type '{value}'")
        return value


class PerformanceClaimGapReport(BaseModel):
    """Deterministic Product-level Performance Claim evidence-gap report."""

    model_config = ConfigDict(extra="forbid")

    product: VersionedObjectReference
    performance_claim_count: int
    sufficient_claim_count: int
    gap_claim_count: int
    complete: bool
    claims: list[PerformanceClaimGapItem]

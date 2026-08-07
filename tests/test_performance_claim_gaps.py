"""Regression tests for Product-scoped Performance Claim evidence gaps."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.performance_gap_service import PerformanceClaimGapService


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _create(repo, object_type: str, payload: dict):
    obj, _ = repo.create_object(object_type, payload, "owner", "owner")
    repo.session.commit()
    return obj


def _approve(repo, obj):
    repo.transition_state(obj.object_uuid, "in_review", "author")
    repo.transition_state(obj.object_uuid, "approved", "approver")
    repo.session.commit()
    return obj


def _product(repo):
    return _create(repo, "product", {"id": "P-GAPS"})


def _claim(repo, identifier: str, claim_type="performance", severity="medium"):
    category = {
        "clinical": "clinical",
        "analytical": "analytical",
        "performance": "clinical",
        "marketing": "marketing",
    }[claim_type]
    return _create(
        repo,
        "claim",
        {
            "claim_type": claim_type,
            "claim_category": category,
            "confidence": "high",
            "severity": severity,
            "jurisdiction": "EU",
            "language": "en",
            "wording": identifier,
            "regulatory_scope": [],
        },
    )


def _link_claim(repo, product, claim):
    relation = repo.create_relation(
        source_uuid=product.object_uuid,
        source_version=product.current_version,
        target_uuid=claim.object_uuid,
        target_version=claim.current_version,
        relation_type="has_claim",
        created_by="owner",
    )
    repo.session.commit()
    return relation


def _evidence(repo, evidence_type: str, quality="high", approved=True):
    evidence = _create(
        repo,
        "evidence",
        {
            "evidence_type": evidence_type,
            "quality_rating": quality,
            "title": f"{evidence_type} evidence",
        },
    )
    return _approve(repo, evidence) if approved else evidence


def _link_evidence(repo, evidence, claim, relation_type="supported_by"):
    relation = repo.create_relation(
        source_uuid=evidence.object_uuid,
        source_version=evidence.current_version,
        target_uuid=claim.object_uuid,
        target_version=claim.current_version,
        relation_type=relation_type,
        created_by="owner",
    )
    repo.session.commit()
    return relation


def _item(report):
    assert report.performance_claim_count == 1
    return report.claims[0]


def _codes(item):
    return {finding.rule_code for finding in item.findings}


def test_only_performance_relevant_claim_types_are_assessed(repo):
    product = _product(repo)
    for claim_type in ("clinical", "analytical", "performance", "marketing"):
        claim = _claim(repo, f"C-{claim_type}", claim_type)
        _link_claim(repo, product, claim)

    report = PerformanceClaimGapService(repo).evaluate_product(product.uuid_hex)

    assert report.performance_claim_count == 3
    assert {item.claim_type for item in report.claims} == {
        "clinical",
        "analytical",
        "performance",
    }
    assert report.gap_claim_count == 3


def test_missing_evidence_is_reported(repo):
    product = _product(repo)
    claim = _claim(repo, "C-MISSING")
    _link_claim(repo, product, claim)

    item = _item(PerformanceClaimGapService(repo).evaluate_product(product.uuid_hex))

    assert item.sufficient is False
    assert item.supporting_evidence_count == 0
    assert _codes(item) == {"PERF-EVID-MISSING-001"}


def test_approved_claim_with_suitable_evidence_is_sufficient(repo):
    product = _product(repo)
    claim = _claim(repo, "C-SUFFICIENT", "clinical")
    _link_claim(repo, product, claim)
    evidence = _evidence(repo, "clinical_study", quality="high")
    _link_evidence(repo, evidence, claim)
    _approve(repo, claim)

    item = _item(PerformanceClaimGapService(repo).evaluate_product(product.uuid_hex))

    assert item.sufficient is True
    assert item.findings == []
    assert item.supporting_evidence_count == 1


def test_unapproved_evidence_is_reported(repo):
    product = _product(repo)
    claim = _claim(repo, "C-DRAFT-EVID", "analytical")
    _link_claim(repo, product, claim)
    evidence = _evidence(repo, "analytical_study", approved=False)
    _link_evidence(repo, evidence, claim)

    item = _item(PerformanceClaimGapService(repo).evaluate_product(product.uuid_hex))

    assert "PERF-EVID-UNAPPROVED-001" in _codes(item)
    assert "PERF-EVID-TYPE-001" in _codes(item)


def test_low_quality_approved_evidence_is_reported(repo):
    product = _product(repo)
    claim = _claim(repo, "C-QUALITY", "performance", severity="high")
    _link_claim(repo, product, claim)
    evidence = _evidence(repo, "clinical_study", quality="medium")
    _link_evidence(repo, evidence, claim)

    item = _item(PerformanceClaimGapService(repo).evaluate_product(product.uuid_hex))

    assert _codes(item) == {"PERF-EVID-QUALITY-001"}


def test_disallowed_evidence_type_is_reported(repo):
    product = _product(repo)
    claim = _claim(repo, "C-TYPE", "analytical")
    _link_claim(repo, product, claim)
    evidence = _evidence(repo, "clinical_study")
    _link_evidence(repo, evidence, claim)

    item = _item(PerformanceClaimGapService(repo).evaluate_product(product.uuid_hex))

    assert _codes(item) == {"PERF-EVID-TYPE-001"}


def test_contradictory_evidence_is_reported(repo):
    product = _product(repo)
    claim = _claim(repo, "C-CONTRA", "clinical")
    _link_claim(repo, product, claim)
    supporting = _evidence(repo, "clinical_study")
    contradicting = _evidence(repo, "clinical_study")
    _link_evidence(repo, supporting, claim)
    _link_evidence(repo, contradicting, claim, relation_type="contradicted_by")

    item = _item(PerformanceClaimGapService(repo).evaluate_product(product.uuid_hex))

    assert _codes(item) == {"PERF-EVID-CONTRADICTION-001"}


def test_stale_product_claim_link_is_reported(repo):
    product = _product(repo)
    claim = _claim(repo, "C-STALE", "clinical")
    _link_claim(repo, product, claim)
    repo.create_version(
        claim.object_uuid,
        {
            "claim_type": "clinical",
            "claim_category": "clinical",
            "confidence": "high",
            "severity": "medium",
            "jurisdiction": "EU",
            "language": "en",
            "wording": "C-STALE-v2",
            "regulatory_scope": [],
        },
        "owner",
    )
    evidence = _evidence(repo, "clinical_study")
    _link_evidence(repo, evidence, claim)
    repo.session.commit()

    item = _item(PerformanceClaimGapService(repo).evaluate_product(product.uuid_hex))

    assert "PERF-CLAIM-LINK-STALE-001" in _codes(item)


def test_product_gap_counts_are_deterministic(repo):
    product = _product(repo)
    sufficient = _claim(repo, "C-B", "performance")
    missing = _claim(repo, "C-A", "performance")
    _link_claim(repo, product, sufficient)
    _link_claim(repo, product, missing)
    evidence = _evidence(repo, "analytical_study")
    _link_evidence(repo, evidence, sufficient)

    report = PerformanceClaimGapService(repo).evaluate_product(product.uuid_hex)

    assert report.performance_claim_count == 2
    assert report.sufficient_claim_count == 1
    assert report.gap_claim_count == 1
    assert report.complete is False
    claim_uuids = [item.claim.object_uuid for item in report.claims]
    assert claim_uuids == sorted(claim_uuids)

"""Regression tests for REP-PER-0004 frozen completeness reporting."""

from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import BaselineValidationError
from orkp.domain.per_completeness_models import PERCompletenessSnapshotPayload
from orkp.domain.per_content_models import PERReportBaselineCreateRequest
from orkp.domain.per_draft_service import PERDraftService
from orkp.domain.per_report_baseline_service import PERReportBaselineService
from orkp.domain.performance_gap_service import PerformanceClaimGapService
from orkp.domain.performance_models import PerformanceStudyCreateRequest
from orkp.domain.performance_report_models import PerformanceReportBaselineCreateRequest
from orkp.domain.performance_report_service import PerformanceReportService
from orkp.domain.performance_result_models import PerformanceResultCreateRequest
from orkp.domain.performance_result_service import PerformanceResultService
from orkp.domain.performance_service import PerformanceStudyService


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _approve(repo, obj):
    repo.transition_state(obj.object_uuid, "in_review", "author")
    repo.transition_state(obj.object_uuid, "approved", "approver")
    repo.session.commit()
    return obj


def _claim_payload(wording: str):
    return {
        "claim_type": "clinical",
        "claim_category": "clinical",
        "confidence": "high",
        "severity": "medium",
        "jurisdiction": "EU",
        "language": "en",
        "wording": wording,
        "regulatory_scope": [],
    }


def _context(repo):
    product, _ = repo.create_object(
        "product",
        {"product_id": "P-COMP", "name": "Completeness Product"},
        "owner",
        "owner",
    )
    _approve(repo, product)

    supported_claim, _ = repo.create_object(
        "claim", _claim_payload("Supported clinical claim"), "owner", "owner"
    )
    missing_claim, _ = repo.create_object(
        "claim", _claim_payload("Missing-evidence clinical claim"), "owner", "owner"
    )
    _approve(repo, supported_claim)
    _approve(repo, missing_claim)

    for claim in (supported_claim, missing_claim):
        repo.create_relation(
            source_uuid=product.object_uuid,
            source_version=1,
            target_uuid=claim.object_uuid,
            target_version=1,
            relation_type="has_claim",
            created_by="owner",
        )
    repo.session.commit()

    study = PerformanceStudyService(repo).create_study(
        product.uuid_hex,
        PerformanceStudyCreateRequest(
            study_id="ST-COMP",
            study_type="clinical",
            title="Clinical completeness study",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            study_status="completed",
            owner_user_id="study-owner",
        ),
    )
    result = PerformanceResultService(repo).create_result(
        study.object_uuid,
        PerformanceResultCreateRequest(
            result_id="R-COMP",
            study={"object_uuid": study.object_uuid, "object_version": 1},
            claims=[{"object_uuid": supported_claim.uuid_hex, "object_version": 1}],
            parameter="clinical sensitivity",
            result_value="99.1",
            quality_rating="high",
            owner_user_id="result-owner",
        ),
    )
    _approve(repo, repo.get_by_uuid_hex(result.object_uuid))

    source_baseline = PerformanceReportService(repo).create_baseline(
        PerformanceReportBaselineCreateRequest(
            name="Completeness source baseline",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            evidence=[{"object_uuid": result.object_uuid, "object_version": 1}],
            created_by_user_id="per-author",
        )
    )
    return product, supported_claim, missing_claim, result, source_baseline


def _report_baseline(repo, source_baseline_uuid: str):
    return PERReportBaselineService(repo).create_baseline(
        PERReportBaselineCreateRequest(
            name="Completeness report baseline",
            performance_baseline_uuid=source_baseline_uuid,
            created_by_user_id="report-author",
        )
    )


def test_report_baseline_freezes_gap_snapshot_and_missing_claim(repo):
    _, _, missing_claim, _, source_baseline = _context(repo)

    response = _report_baseline(repo, source_baseline.baseline_uuid)

    items = repo.list_baseline_items(UUID(response.baseline_uuid).bytes)
    completeness_items = [
        item for item in items if item.object_type == "report_completeness"
    ]
    assert response.ai_draft_block_count == 0
    assert len(completeness_items) == 1
    assert any(item.object_uuid == missing_claim.object_uuid for item in items)

    payload = PERCompletenessSnapshotPayload(**completeness_items[0].snapshot_json)
    assert payload.gap_report.performance_claim_count == 2
    assert payload.gap_report.gap_claim_count == 1
    missing = next(
        item
        for item in payload.gap_report.claims
        if item.claim.object_uuid == missing_claim.uuid_hex
    )
    assert {finding.rule_code for finding in missing.findings} == {
        "PERF-EVID-MISSING-001"
    }


def test_draft_uses_frozen_completeness_after_live_gap_is_resolved(repo, monkeypatch):
    _, _, missing_claim, _, source_baseline = _context(repo)
    report_baseline = _report_baseline(repo, source_baseline.baseline_uuid)
    service = PERDraftService(repo)
    first = service.generate_draft(report_baseline.baseline_uuid, "report-generator")

    evidence, _ = repo.create_object(
        "evidence",
        {
            "evidence_type": "clinical_study",
            "quality_rating": "high",
            "title": "Later supporting evidence",
        },
        "owner",
        "owner",
    )
    _approve(repo, evidence)
    repo.create_relation(
        source_uuid=evidence.object_uuid,
        source_version=1,
        target_uuid=missing_claim.object_uuid,
        target_version=1,
        relation_type="supported_by",
        created_by="owner",
    )
    repo.session.commit()
    assert PerformanceClaimGapService(repo).evaluate_product(
        first.draft.product.object_uuid
    ).complete

    monkeypatch.setattr(
        PerformanceClaimGapService,
        "evaluate_product",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live gap read")),
    )
    second = service.generate_draft(report_baseline.baseline_uuid, "report-generator")

    assert first.draft.schema_version == "per-draft-1.2"
    assert first.draft.completeness_report is not None
    assert first.draft.completeness_report.gap_report.gap_claim_count == 1
    assert first.canonical_json == second.canonical_json
    assert first.checksum_sha256 == second.checksum_sha256


def test_stale_source_product_is_rejected_for_completeness(repo, monkeypatch):
    _, _, _, _, source_baseline = _context(repo)
    real_evaluate = PerformanceClaimGapService.evaluate_product

    def stale_evaluate(service, product_hex):
        report = real_evaluate(service, product_hex)
        return report.model_copy(
            update={
                "product": report.product.model_copy(
                    update={"object_version": report.product.object_version + 1}
                )
            }
        )

    monkeypatch.setattr(PerformanceClaimGapService, "evaluate_product", stale_evaluate)

    with pytest.raises(BaselineValidationError, match="stale for completeness"):
        _report_baseline(repo, source_baseline.baseline_uuid)

    assert repo.list_objects(object_type="report_completeness") == []


def test_generator_rejects_completeness_missing_frozen_claim_context(repo):
    _, _, missing_claim, _, source_baseline = _context(repo)
    report_baseline = _report_baseline(repo, source_baseline.baseline_uuid)
    items = repo.list_baseline_items(UUID(report_baseline.baseline_uuid).bytes)
    object_versions = [
        (item.object_uuid, item.version_no)
        for item in items
        if item.object_uuid != missing_claim.object_uuid
    ]
    tampered = repo.create_baseline(
        "Completeness missing Claim",
        None,
        object_versions,
        "report-author",
    )
    repo.session.commit()

    with pytest.raises(BaselineValidationError, match="Claim outside the baseline"):
        PERDraftService(repo).generate_draft(
            UUID(bytes=tampered.baseline_uuid).hex,
            "report-generator",
        )


def test_generator_rejects_duplicate_completeness_snapshots(repo):
    _, _, _, _, source_baseline = _context(repo)
    report_baseline = _report_baseline(repo, source_baseline.baseline_uuid)
    items = repo.list_baseline_items(UUID(report_baseline.baseline_uuid).bytes)
    completeness_item = next(
        item for item in items if item.object_type == "report_completeness"
    )
    duplicate, _ = repo.create_object(
        "report_completeness",
        dict(completeness_item.snapshot_json),
        "report-author",
        "report-author",
    )
    object_versions = [(item.object_uuid, item.version_no) for item in items]
    object_versions.append((duplicate.object_uuid, 1))
    tampered = repo.create_baseline(
        "Duplicate completeness",
        None,
        object_versions,
        "report-author",
    )
    repo.session.commit()

    with pytest.raises(BaselineValidationError, match="exactly one completeness"):
        PERDraftService(repo).generate_draft(
            UUID(bytes=tampered.baseline_uuid).hex,
            "report-generator",
        )

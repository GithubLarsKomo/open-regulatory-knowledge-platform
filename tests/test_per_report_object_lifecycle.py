"""Regression tests for persisted PER report aggregates and lifecycle."""

import hashlib
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    BaselineValidationError,
    ImmutableVersionError,
    SelfApprovalNotAllowedError,
)
from orkp.domain.per_content_models import PERReportBaselineCreateRequest
from orkp.domain.per_report_object_models import (
    PERReportCreateRequest,
    PERReportObjectPayload,
    PERReportRegenerateRequest,
)
from orkp.domain.per_report_object_service import PERReportObjectService
from orkp.domain.per_report_baseline_service import PERReportBaselineService
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


def _approve(repo, obj, actor="approver"):
    repo.transition_state(obj.object_uuid, "in_review", "author")
    repo.transition_state(obj.object_uuid, "approved", actor)
    repo.session.commit()
    return obj


def _context(repo):
    product, _ = repo.create_object(
        "product",
        {"product_id": "P-REPORT-OBJ", "name": "Persisted PER Product"},
        "owner",
        "owner",
    )
    _approve(repo, product)
    claim, _ = repo.create_object(
        "claim",
        {
            "claim_type": "clinical",
            "claim_category": "clinical",
            "confidence": "high",
            "severity": "medium",
            "jurisdiction": "EU",
            "language": "en",
            "wording": "Persisted clinical claim",
            "regulatory_scope": [],
        },
        "claim-owner",
        "claim-owner",
    )
    _approve(repo, claim)
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
            study_id="ST-REPORT-OBJ",
            study_type="clinical",
            title="Persisted report study",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            study_status="completed",
            owner_user_id="study-owner",
        ),
    )
    result = PerformanceResultService(repo).create_result(
        study.object_uuid,
        PerformanceResultCreateRequest(
            result_id="R-REPORT-OBJ",
            study={"object_uuid": study.object_uuid, "object_version": 1},
            claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
            parameter="clinical sensitivity",
            result_value="99.6",
            interpretation="Frozen approved interpretation.",
            quality_rating="high",
            owner_user_id="result-owner",
        ),
    )
    _approve(repo, repo.get_by_uuid_hex(result.object_uuid))
    source_baseline = PerformanceReportService(repo).create_baseline(
        PerformanceReportBaselineCreateRequest(
            name="Persisted report source baseline",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            evidence=[{"object_uuid": result.object_uuid, "object_version": 1}],
            created_by_user_id="per-author",
        )
    )
    report_baseline = PERReportBaselineService(repo).create_baseline(
        PERReportBaselineCreateRequest(
            name="Persisted PER report baseline",
            performance_baseline_uuid=source_baseline.baseline_uuid,
            created_by_user_id="report-author",
        )
    )
    return product, claim, study, result, source_baseline, report_baseline


def _create_report(repo, product, report_baseline, report_type="PER"):
    return PERReportObjectService(repo).create_report(
        PERReportCreateRequest(
            product_uuid=product.uuid_hex,
            baseline_uuid=report_baseline.baseline_uuid,
            report_type=report_type,
            owner_user_id="report-owner",
        )
    )


def _fresh_report_baseline(repo, source_baseline):
    return PERReportBaselineService(repo).create_baseline(
        PERReportBaselineCreateRequest(
            name="Regenerated PER report baseline",
            performance_baseline_uuid=source_baseline.baseline_uuid,
            created_by_user_id="report-regenerator",
        )
    )


def test_create_persists_stable_report_object_and_canonical_snapshot(repo):
    product, _, _, _, _, report_baseline = _context(repo)

    response = _create_report(repo, product, report_baseline, report_type="PER-addendum")

    report = repo.get_by_uuid_hex(response.report_uuid)
    assert report is not None
    assert report.object_type == "report"
    assert report.current_version == 1
    assert report.lifecycle_state == "draft"
    version = repo.get_version(report.object_uuid, 1)
    payload = PERReportObjectPayload(**version.payload_json)
    assert payload.report_type == "PER-addendum"
    assert payload.product.object_uuid == product.uuid_hex
    assert payload.baseline_uuid == report_baseline.baseline_uuid
    assert payload.draft.schema_version == "per-draft-1.3"
    assert payload.draft.section_coverage is not None
    assert len(payload.draft.section_coverage.sections) == 10

    canonical = PERReportObjectService(repo).get_canonical_json(response.report_uuid)
    assert canonical.object_version == 1
    assert canonical.canonical_checksum_sha256 == hashlib.sha256(
        canonical.canonical_json.encode("utf-8")
    ).hexdigest()
    assert canonical.canonical_checksum_sha256 == response.canonical_checksum_sha256


def test_raw_performance_baseline_cannot_create_persisted_report(repo):
    product, _, _, _, source_baseline, _ = _context(repo)

    with pytest.raises(BaselineValidationError, match="derived Report baseline"):
        PERReportObjectService(repo).create_report(
            PERReportCreateRequest(
                product_uuid=product.uuid_hex,
                baseline_uuid=source_baseline.baseline_uuid,
                owner_user_id="report-owner",
            )
        )

    assert repo.list_objects(object_type="report") == []


def test_report_product_must_match_frozen_baseline_product(repo):
    _, _, _, _, _, report_baseline = _context(repo)
    other_product, _ = repo.create_object(
        "product",
        {"product_id": "P-OTHER", "name": "Other Product"},
        "other-owner",
        "other-owner",
    )
    repo.session.commit()

    with pytest.raises(BaselineValidationError, match="does not match"):
        PERReportObjectService(repo).create_report(
            PERReportCreateRequest(
                product_uuid=other_product.uuid_hex,
                baseline_uuid=report_baseline.baseline_uuid,
                owner_user_id="report-owner",
            )
        )

    assert repo.list_objects(object_type="report") == []


def test_draft_regeneration_creates_new_version_same_report_uuid(repo):
    product, _, _, _, source_baseline, report_baseline = _context(repo)
    original = _create_report(repo, product, report_baseline)
    regenerated_baseline = _fresh_report_baseline(repo, source_baseline)

    regenerated = PERReportObjectService(repo).regenerate_report(
        original.report_uuid,
        PERReportRegenerateRequest(
            baseline_uuid=regenerated_baseline.baseline_uuid,
            actor_user_id="report-owner",
        ),
    )

    assert regenerated.report_uuid == original.report_uuid
    assert regenerated.object_version == 2
    assert regenerated.lifecycle_state == "draft"
    assert regenerated.baseline_uuid == regenerated_baseline.baseline_uuid
    assert len(repo.list_versions(repo.get_by_uuid_hex(original.report_uuid).object_uuid)) == 2


def test_report_approval_is_four_eyes_and_approved_version_is_immutable(repo):
    product, _, _, _, _, report_baseline = _context(repo)
    report = _create_report(repo, product, report_baseline)
    service = PERReportObjectService(repo)

    submitted = service.submit_for_review(report.report_uuid, "report-owner")
    assert submitted.lifecycle_state == "in_review"

    with pytest.raises(SelfApprovalNotAllowedError):
        service.approve(report.report_uuid, "report-owner")

    approved = service.approve(report.report_uuid, "independent-approver", "Reviewed")
    assert approved.lifecycle_state == "approved"
    report_object = repo.get_by_uuid_hex(report.report_uuid)
    with pytest.raises(ImmutableVersionError):
        repo.create_version(
            report_object.object_uuid,
            approved.draft.model_dump(mode="json"),
            "report-owner",
        )


def test_regeneration_after_approval_creates_successor_report(repo):
    product, _, _, _, source_baseline, report_baseline = _context(repo)
    original = _create_report(repo, product, report_baseline)
    service = PERReportObjectService(repo)
    service.submit_for_review(original.report_uuid, "report-owner")
    approved = service.approve(original.report_uuid, "independent-approver")
    regenerated_baseline = _fresh_report_baseline(repo, source_baseline)

    successor = service.regenerate_report(
        original.report_uuid,
        PERReportRegenerateRequest(
            baseline_uuid=regenerated_baseline.baseline_uuid,
            actor_user_id="successor-owner",
        ),
    )

    assert successor.report_uuid != original.report_uuid
    assert successor.object_version == 1
    assert successor.lifecycle_state == "draft"
    assert successor.owner_user_id == "successor-owner"
    assert successor.predecessor_report is not None
    assert successor.predecessor_report.object_uuid == original.report_uuid
    assert successor.predecessor_report.object_version == approved.object_version
    assert service.get_report(original.report_uuid).lifecycle_state == "approved"


def test_persisted_canonical_json_is_independent_of_later_frozen_input_versions(repo):
    product, _, _, _, _, report_baseline = _context(repo)
    report = _create_report(repo, product, report_baseline)
    service = PERReportObjectService(repo)
    before = service.get_canonical_json(report.report_uuid)

    items = repo.list_baseline_items(UUID(report_baseline.baseline_uuid).bytes)
    completeness_item = next(
        item for item in items if item.object_type == "report_completeness"
    )
    completeness_object = repo.get_by_uuid(completeness_item.object_uuid)
    changed_payload = dict(completeness_item.snapshot_json)
    changed_payload["owner_user_id"] = "later-completeness-author"
    repo.create_version(
        completeness_object.object_uuid,
        changed_payload,
        "later-completeness-author",
    )
    repo.session.commit()

    after = service.get_canonical_json(report.report_uuid)
    assert before.canonical_json == after.canonical_json
    assert before.canonical_checksum_sha256 == after.canonical_checksum_sha256
    assert "later-completeness-author" not in after.canonical_json

"""Regression tests for REP-PER-0003 content provenance and derived baselines."""

from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import BaselineValidationError
from orkp.domain.per_content_models import (
    PERReportBaselineCreateRequest,
    PERReportContentPayload,
)
from orkp.domain.per_draft_service import PERDraftService
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


def _approve(repo, obj):
    repo.transition_state(obj.object_uuid, "in_review", "author")
    repo.transition_state(obj.object_uuid, "approved", "approver")
    repo.session.commit()
    return obj


def _performance_baseline(repo):
    product, _ = repo.create_object(
        "product",
        {"product_id": "P-CONTENT", "name": "PER content product"},
        "owner",
        "owner",
    )
    _approve(repo, product)
    claim, _ = repo.create_object(
        "claim",
        {"claim_id": "C-CONTENT", "wording": "Clinical performance claim"},
        "owner",
        "owner",
    )
    _approve(repo, claim)
    study = PerformanceStudyService(repo).create_study(
        product.uuid_hex,
        PerformanceStudyCreateRequest(
            study_id="ST-CONTENT",
            study_type="clinical",
            title="Clinical content study",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            study_status="completed",
            owner_user_id="study-owner",
        ),
    )
    result = PerformanceResultService(repo).create_result(
        study.object_uuid,
        PerformanceResultCreateRequest(
            result_id="R-CONTENT",
            study={"object_uuid": study.object_uuid, "object_version": 1},
            claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
            parameter="clinical sensitivity",
            result_value="98.9",
            interpretation="Approved source interpretation.",
            quality_rating="high",
            owner_user_id="result-owner",
        ),
    )
    _approve(repo, repo.get_by_uuid_hex(result.object_uuid))
    baseline = PerformanceReportService(repo).create_baseline(
        PerformanceReportBaselineCreateRequest(
            name="Performance source baseline",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            evidence=[{"object_uuid": result.object_uuid, "object_version": 1}],
            created_by_user_id="per-author",
        )
    )
    return product, claim, study, result, baseline


def _derived_request(source_baseline_uuid: str, result_uuid: str):
    return PERReportBaselineCreateRequest(
        name="PER authoring baseline",
        performance_baseline_uuid=source_baseline_uuid,
        ai_draft_blocks=[
            {
                "block_id": "ai-clinical-summary",
                "section_type": "clinical_performance",
                "text": "AI-generated clinical narrative.",
                "model_id": "external-model-v1",
                "source_refs": [
                    {"object_uuid": result_uuid, "object_version": 1}
                ],
            }
        ],
        created_by_user_id="report-author",
    )


def test_derived_baseline_freezes_ai_content_and_original_items(repo):
    *_, result, source_baseline = _performance_baseline(repo)
    source_items = repo.list_baseline_items(UUID(source_baseline.baseline_uuid).bytes)

    response = PERReportBaselineService(repo).create_baseline(
        _derived_request(source_baseline.baseline_uuid, result.object_uuid)
    )

    derived_items = repo.list_baseline_items(UUID(response.baseline_uuid).bytes)
    content_items = [
        item for item in derived_items if item.object_type == "report_content"
    ]
    assert response.item_count == len(source_items) + 1
    assert response.ai_draft_block_count == 1
    assert len(content_items) == 1
    payload = PERReportContentPayload(**content_items[0].snapshot_json)
    assert payload.origin == "ai_draft"
    assert payload.review_status == "unapproved_draft"
    assert payload.model_id == "external-model-v1"
    assert payload.source_refs[0].object_uuid == result.object_uuid
    content_object = repo.get_by_uuid(content_items[0].object_uuid)
    assert content_object.lifecycle_state == "draft"


def test_ai_source_outside_performance_baseline_is_rejected_atomically(repo):
    *_, _, source_baseline = _performance_baseline(repo)
    unrelated, _ = repo.create_object(
        "evidence",
        {"evidence_type": "literature", "title": "Unfrozen evidence"},
        "owner",
        "owner",
    )
    repo.session.commit()
    request = PERReportBaselineCreateRequest(
        name="Invalid PER authoring baseline",
        performance_baseline_uuid=source_baseline.baseline_uuid,
        ai_draft_blocks=[
            {
                "block_id": "ai-invalid-source",
                "section_type": "clinical_performance",
                "text": "AI draft with an unfrozen source.",
                "model_id": "external-model-v1",
                "source_refs": [
                    {"object_uuid": unrelated.uuid_hex, "object_version": 1}
                ],
            }
        ],
        created_by_user_id="report-author",
    )

    with pytest.raises(BaselineValidationError, match="not frozen"):
        PERReportBaselineService(repo).create_baseline(request)

    assert repo.list_objects(object_type="report_content") == []


def test_duplicate_ai_block_ids_are_rejected():
    block = {
        "block_id": "duplicate",
        "section_type": "clinical_performance",
        "text": "Draft",
        "model_id": "model-v1",
        "source_refs": [
            {
                "object_uuid": "00000000000000000000000000000001",
                "object_version": 1,
            }
        ],
    }
    with pytest.raises(ValidationError, match="duplicate block_id"):
        PERReportBaselineCreateRequest(
            name="Duplicate blocks",
            performance_baseline_uuid="00000000000000000000000000000002",
            ai_draft_blocks=[block, block],
            created_by_user_id="report-author",
        )


def test_generated_draft_distinguishes_approved_and_ai_content(repo):
    *_, result, source_baseline = _performance_baseline(repo)
    report_baseline = PERReportBaselineService(repo).create_baseline(
        _derived_request(source_baseline.baseline_uuid, result.object_uuid)
    )

    generated = PERDraftService(repo).generate_draft(
        report_baseline.baseline_uuid,
        "report-generator",
    )

    assert generated.draft.schema_version == "per-draft-1.1"
    assert len(generated.draft.content_blocks) == 2
    approved, ai_draft = generated.draft.content_blocks
    assert approved.origin == "approved_source"
    assert approved.review_status == "source_approved"
    assert approved.text == "Approved source interpretation."
    assert approved.model_id is None
    assert approved.source_refs[0].object_uuid == result.object_uuid
    assert ai_draft.origin == "ai_draft"
    assert ai_draft.review_status == "unapproved_draft"
    assert ai_draft.text == "AI-generated clinical narrative."
    assert ai_draft.model_id == "external-model-v1"
    assert ai_draft.source_refs[0].object_uuid == result.object_uuid


def test_report_content_live_version_does_not_change_frozen_draft(repo):
    *_, result, source_baseline = _performance_baseline(repo)
    report_baseline = PERReportBaselineService(repo).create_baseline(
        _derived_request(source_baseline.baseline_uuid, result.object_uuid)
    )
    service = PERDraftService(repo)
    first = service.generate_draft(report_baseline.baseline_uuid, "report-generator")

    items = repo.list_baseline_items(UUID(report_baseline.baseline_uuid).bytes)
    content_item = next(item for item in items if item.object_type == "report_content")
    content_object = repo.get_by_uuid(content_item.object_uuid)
    changed_payload = dict(content_item.snapshot_json)
    changed_payload["text"] = "Changed after report baseline freeze."
    repo.create_version(
        content_object.object_uuid,
        changed_payload,
        "report-author",
    )
    repo.session.commit()

    second = service.generate_draft(report_baseline.baseline_uuid, "report-generator")

    assert first.canonical_json == second.canonical_json
    assert first.checksum_sha256 == second.checksum_sha256
    assert "Changed after report baseline freeze." not in second.canonical_json


def test_generator_rejects_report_content_with_unfrozen_source(repo):
    *_, _, source_baseline = _performance_baseline(repo)
    unrelated, _ = repo.create_object(
        "evidence",
        {"evidence_type": "literature", "title": "Outside source"},
        "owner",
        "owner",
    )
    content_payload = PERReportContentPayload(
        block_id="tampered-ai-block",
        section_type="clinical_performance",
        text="Tampered AI narrative.",
        model_id="external-model-v1",
        source_performance_baseline_uuid=source_baseline.baseline_uuid,
        source_refs=[{"object_uuid": unrelated.uuid_hex, "object_version": 1}],
        owner_user_id="report-author",
    )
    content_object, _ = repo.create_object(
        "report_content",
        content_payload.model_dump(mode="json"),
        "report-author",
        "report-author",
    )
    source_items = repo.list_baseline_items(UUID(source_baseline.baseline_uuid).bytes)
    object_versions = [
        (item.object_uuid, item.version_no) for item in source_items
    ] + [(content_object.object_uuid, 1)]
    tampered_baseline = repo.create_baseline(
        "Tampered report baseline",
        None,
        object_versions,
        "report-author",
    )
    repo.session.commit()

    with pytest.raises(BaselineValidationError, match="outside the frozen Performance"):
        PERDraftService(repo).generate_draft(
            UUID(bytes=tampered_baseline.baseline_uuid).hex,
            "report-generator",
        )

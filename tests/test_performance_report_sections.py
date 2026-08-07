"""Regression tests for reproducible Performance Evaluation sections."""

import hashlib
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from orkp.db.models import Base, EventLog, GeneratedArtifact
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import BaselineValidationError
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


def _create_object(repo, object_type: str, payload: dict):
    obj, _ = repo.create_object(object_type, payload, "owner", "owner")
    repo.session.commit()
    return obj


def _approve(repo, obj):
    repo.transition_state(obj.object_uuid, "in_review", "author")
    repo.transition_state(obj.object_uuid, "approved", "approver")
    repo.session.commit()
    return obj


def _product(repo, approved=True):
    product = _create_object(
        repo, "product", {"product_id": "P-PER", "name": "PER Product"}
    )
    return _approve(repo, product) if approved else product


def _claim(repo, identifier: str, approved=True):
    claim = _create_object(
        repo, "claim", {"claim_id": identifier, "wording": identifier}
    )
    return _approve(repo, claim) if approved else claim


def _study(repo, product, study_type: str):
    request = PerformanceStudyCreateRequest(
        study_id=f"ST-{study_type}",
        study_type=study_type,
        title=f"{study_type} study",
        product={
            "object_uuid": product.uuid_hex,
            "object_version": product.current_version,
        },
        study_status="completed",
        owner_user_id="study-owner",
    )
    return PerformanceStudyService(repo).create_study(product.uuid_hex, request)


def _source(repo, identifier="SRC-1"):
    return _create_object(
        repo,
        "evidence",
        {"evidence_type": "internal_document", "title": identifier},
    )


def _result(repo, study, claim, source=None):
    kwargs = {}
    if source is not None:
        kwargs = {
            "statistical_method": "Wilson 95% CI",
            "statistical_sources": [
                {
                    "source_kind": "source_data",
                    "evidence": {
                        "object_uuid": source.uuid_hex,
                        "object_version": source.current_version,
                    },
                }
            ],
        }
    request = PerformanceResultCreateRequest(
        result_id=f"R-{study.payload.study_type}-{claim.uuid_hex[:6]}",
        study={
            "object_uuid": study.object_uuid,
            "object_version": study.object_version,
        },
        claims=[
            {"object_uuid": claim.uuid_hex, "object_version": claim.current_version}
        ],
        parameter="performance parameter",
        result_value="98.5",
        quality_rating="high",
        owner_user_id="result-owner",
        **kwargs,
    )
    response = PerformanceResultService(repo).create_result(study.object_uuid, request)
    result = repo.get_by_uuid_hex(response.object_uuid)
    _approve(repo, result)
    return response


def _baseline_request(product, *results):
    return PerformanceReportBaselineCreateRequest(
        name="PER baseline",
        description="Frozen Performance Evaluation inputs",
        product={
            "object_uuid": product.uuid_hex,
            "object_version": product.current_version,
        },
        evidence=[
            {"object_uuid": result.object_uuid, "object_version": result.object_version}
            for result in results
        ],
        created_by_user_id="per-author",
    )


def test_per_baseline_requires_approved_product(repo):
    product = _product(repo, approved=False)
    claim = _claim(repo, "C-PRODUCT")
    study = _study(repo, product, "analytical")
    result = _result(repo, study, claim)

    with pytest.raises(Exception, match="state 'draft'"):
        PerformanceReportService(repo).create_baseline(
            _baseline_request(product, result)
        )


def test_per_baseline_requires_approved_performance_result(repo):
    product = _product(repo)
    claim = _claim(repo, "C-RESULT")
    study = _study(repo, product, "clinical")
    request = PerformanceResultCreateRequest(
        result_id="R-DRAFT",
        study={"object_uuid": study.object_uuid, "object_version": 1},
        claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
        parameter="sensitivity",
        result_value="98.0",
        owner_user_id="result-owner",
    )
    result = PerformanceResultService(repo).create_result(study.object_uuid, request)

    with pytest.raises(Exception, match="state 'draft'"):
        PerformanceReportService(repo).create_baseline(
            _baseline_request(product, result)
        )


def test_per_baseline_requires_current_approved_claim(repo):
    product = _product(repo)
    claim = _claim(repo, "C-DRAFT", approved=False)
    study = _study(repo, product, "clinical")
    result = _result(repo, study, claim)

    with pytest.raises(Exception, match="state 'draft'"):
        PerformanceReportService(repo).create_baseline(
            _baseline_request(product, result)
        )


def test_per_baseline_freezes_transitive_study_claim_and_statistical_source(repo):
    product = _product(repo)
    claim = _claim(repo, "C-FREEZE")
    study = _study(repo, product, "analytical")
    source = _source(repo, "Raw dataset")
    result = _result(repo, study, claim, source)

    baseline = PerformanceReportService(repo).create_baseline(
        _baseline_request(product, result)
    )
    items = repo.list_baseline_items(UUID(baseline.baseline_uuid).bytes)
    frozen = {(item.object_type, UUID(bytes=item.object_uuid).hex) for item in items}

    assert baseline.item_count == 5
    assert ("product", product.uuid_hex) in frozen
    assert ("claim", claim.uuid_hex) in frozen
    assert ("study", study.object_uuid) in frozen
    assert ("evidence", result.object_uuid) in frozen
    assert ("evidence", source.uuid_hex) in frozen


def test_per_baseline_rejects_conflicting_versions_of_same_study(repo):
    product = _product(repo)
    claim = _claim(repo, "C-CONFLICT")
    study_v1 = _study(repo, product, "analytical")
    result_v1 = _result(repo, study_v1, claim)

    study_obj = repo.get_by_uuid_hex(study_v1.object_uuid)
    repo.create_version(
        study_obj.object_uuid,
        {**study_v1.payload.model_dump(), "title": "Study v2"},
        "study-owner",
    )
    repo.session.commit()
    study_v2 = PerformanceStudyService(repo).get_study(study_v1.object_uuid, 2)
    result_v2 = _result(repo, study_v2, claim)

    with pytest.raises(BaselineValidationError, match="conflicting versions"):
        PerformanceReportService(repo).create_baseline(
            _baseline_request(product, result_v1, result_v2)
        )


def test_per_generation_groups_three_section_types_deterministically(repo):
    product = _product(repo)
    results = []
    for study_type in ("clinical", "scientific_validity", "analytical"):
        claim = _claim(repo, f"C-{study_type}")
        study = _study(repo, product, study_type)
        results.append(_result(repo, study, claim))

    service = PerformanceReportService(repo)
    baseline = service.create_baseline(_baseline_request(product, *results))
    generated = service.generate_sections(baseline.baseline_uuid, "per-generator")

    assert [section.section_type for section in generated.report.sections] == [
        "scientific_validity",
        "analytical_performance",
        "clinical_performance",
    ]
    assert all(len(section.items) == 1 for section in generated.report.sections)
    assert generated.report.product.object_uuid == product.uuid_hex


def test_per_generation_is_stable_after_live_provenance_changes(repo):
    product = _product(repo)
    claim = _claim(repo, "C-STABLE")
    study = _study(repo, product, "analytical")
    source = _source(repo, "Frozen source")
    result = _result(repo, study, claim, source)
    service = PerformanceReportService(repo)
    baseline = service.create_baseline(_baseline_request(product, result))
    first = service.generate_sections(baseline.baseline_uuid, "per-generator")

    study_obj = repo.get_by_uuid_hex(study.object_uuid)
    repo.create_version(
        study_obj.object_uuid,
        {**study.payload.model_dump(), "title": "Changed after freeze"},
        "study-owner",
    )
    repo.create_version(
        source.object_uuid,
        {"evidence_type": "internal_document", "title": "Changed source"},
        "owner",
    )
    repo.session.commit()

    second = service.generate_sections(baseline.baseline_uuid, "per-generator")

    assert first.canonical_json == second.canonical_json
    assert first.checksum_sha256 == second.checksum_sha256
    assert first.artifact_uuid != second.artifact_uuid
    assert "Changed after freeze" not in second.canonical_json
    assert "Changed source" not in second.canonical_json


def test_per_generation_checksum_artifact_and_audit_event(repo):
    product = _product(repo)
    claim = _claim(repo, "C-AUDIT")
    study = _study(repo, product, "scientific_validity")
    result = _result(repo, study, claim)
    service = PerformanceReportService(repo)
    baseline = service.create_baseline(_baseline_request(product, result))

    generated = service.generate_sections(baseline.baseline_uuid, "per-generator")

    assert (
        generated.checksum_sha256
        == hashlib.sha256(generated.canonical_json.encode("utf-8")).hexdigest()
    )
    artifacts = list(repo.session.execute(select(GeneratedArtifact)).scalars().all())
    assert len(artifacts) == 1
    assert artifacts[0].artifact_type == "performance_evaluation_sections"
    assert artifacts[0].checksum == generated.checksum_sha256

    events = list(
        repo.session.execute(
            select(EventLog).where(EventLog.event_type == "artifact_generated")
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].aggregate_uuid == UUID(baseline.baseline_uuid).bytes

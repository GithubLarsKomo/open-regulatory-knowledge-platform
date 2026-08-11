"""Regression tests for reproducible baseline-only PER draft manifests."""

import hashlib
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from orkp.db.models import Base, GeneratedArtifact
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import BaselineValidationError
from orkp.domain.per_draft_service import PERDraftService
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


def _context(repo, with_statistical_source=True):
    product, _ = repo.create_object(
        "product",
        {"product_id": "P-REP", "name": "PER Report Product"},
        "owner",
        "owner",
    )
    _approve(repo, product)
    claim, _ = repo.create_object(
        "claim",
        {"claim_id": "C-REP", "wording": "Clinical performance claim"},
        "owner",
        "owner",
    )
    _approve(repo, claim)
    study = PerformanceStudyService(repo).create_study(
        product.uuid_hex,
        PerformanceStudyCreateRequest(
            study_id="ST-REP",
            study_type="clinical",
            title="Clinical report study",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            study_status="completed",
            owner_user_id="study-owner",
        ),
    )

    statistical_source = None
    kwargs = {}
    if with_statistical_source:
        statistical_source, _ = repo.create_object(
            "evidence",
            {"evidence_type": "internal_document", "title": "Frozen source data"},
            "owner",
            "owner",
        )
        repo.session.commit()
        kwargs = {
            "statistical_method": "Wilson 95% CI",
            "statistical_sources": [
                {
                    "source_kind": "source_data",
                    "evidence": {
                        "object_uuid": statistical_source.uuid_hex,
                        "object_version": 1,
                    },
                }
            ],
        }

    result = PerformanceResultService(repo).create_result(
        study.object_uuid,
        PerformanceResultCreateRequest(
            result_id="R-REP",
            study={"object_uuid": study.object_uuid, "object_version": 1},
            claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
            parameter="clinical sensitivity",
            result_value="98.7",
            quality_rating="high",
            owner_user_id="result-owner",
            **kwargs,
        ),
    )
    result_obj = repo.get_by_uuid_hex(result.object_uuid)
    _approve(repo, result_obj)
    baseline = PerformanceReportService(repo).create_baseline(
        PerformanceReportBaselineCreateRequest(
            name="PER draft baseline",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            evidence=[{"object_uuid": result.object_uuid, "object_version": 1}],
            created_by_user_id="per-author",
        )
    )
    return product, claim, study, statistical_source, result, baseline


def test_performance_report_builder_has_no_artifact_side_effect(repo):
    *_, baseline = _context(repo, with_statistical_source=False)

    report = PerformanceReportService(repo).build_report(baseline.baseline_uuid)

    assert report.schema_version == "per-sections-1.0"
    artifacts = list(repo.session.execute(select(GeneratedArtifact)).scalars().all())
    assert artifacts == []


def test_per_draft_contains_exact_traceability_and_single_artifact(repo):
    _, claim, study, source, result, baseline = _context(repo)

    generated = PERDraftService(repo).generate_draft(
        baseline.baseline_uuid,
        "report-generator",
    )

    assert generated.draft.schema_version == "per-draft-1.0"
    assert generated.draft.performance_sections.sections[0].section_type == (
        "clinical_performance"
    )
    trace = generated.draft.traceability_appendix
    assert len(trace) == 1
    assert trace[0].performance_result.object_uuid == result.object_uuid
    assert trace[0].study.object_uuid == study.object_uuid
    assert [reference.object_uuid for reference in trace[0].claims] == [claim.uuid_hex]
    assert [reference.object_uuid for reference in trace[0].statistical_sources] == [
        source.uuid_hex
    ]
    assert generated.checksum_sha256 == hashlib.sha256(
        generated.canonical_json.encode("utf-8")
    ).hexdigest()

    artifacts = list(repo.session.execute(select(GeneratedArtifact)).scalars().all())
    assert len(artifacts) == 1
    assert artifacts[0].artifact_type == "per_draft"
    assert artifacts[0].baseline_uuid == UUID(baseline.baseline_uuid).bytes


def test_per_draft_is_stable_after_live_provenance_changes(repo):
    _, _, study, source, _, baseline = _context(repo)
    service = PERDraftService(repo)
    first = service.generate_draft(baseline.baseline_uuid, "report-generator")

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

    second = service.generate_draft(baseline.baseline_uuid, "report-generator")

    assert first.canonical_json == second.canonical_json
    assert first.checksum_sha256 == second.checksum_sha256
    assert first.artifact_uuid != second.artifact_uuid
    assert "Changed after freeze" not in second.canonical_json
    assert "Changed source" not in second.canonical_json


def test_per_draft_rejects_non_performance_baseline(repo):
    product, _ = repo.create_object("product", {"id": "P-NON-PER"}, "owner", "owner")
    repo.session.commit()
    baseline = repo.create_baseline(
        "Not a Performance baseline",
        None,
        [(product.object_uuid, 1)],
        "report-author",
    )
    repo.session.commit()

    with pytest.raises(BaselineValidationError, match="no Performance Results"):
        PERDraftService(repo).generate_draft(
            UUID(bytes=baseline.baseline_uuid).hex,
            "report-generator",
        )

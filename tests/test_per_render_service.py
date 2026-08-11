"""Regression tests for deterministic PER HTML, DOCX and PDF rendering."""

import hashlib
import io
import zipfile

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from orkp.db.models import Base, EventLog, GeneratedArtifact
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import BaselineValidationError
from orkp.domain.per_content_models import PERReportBaselineCreateRequest
from orkp.domain.per_draft_service import PERDraftService
from orkp.domain.per_render_service import PERRenderService
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


def _report_baseline(repo, ai_text="AI clinical summary."):
    product, _ = repo.create_object(
        "product",
        {"product_id": "P-RENDER", "name": "Render Product"},
        "owner",
        "owner",
    )
    _approve(repo, product)
    claim, _ = repo.create_object(
        "claim",
        _claim_payload("Clinical performance claim"),
        "owner",
        "owner",
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
            study_id="ST-RENDER",
            study_type="clinical",
            title="Clinical render study",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            study_status="completed",
            owner_user_id="study-owner",
        ),
    )
    result = PerformanceResultService(repo).create_result(
        study.object_uuid,
        PerformanceResultCreateRequest(
            result_id="R-RENDER",
            study={"object_uuid": study.object_uuid, "object_version": 1},
            claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
            parameter="clinical sensitivity",
            result_value="99.3",
            interpretation="Approved clinical interpretation.",
            quality_rating="high",
            owner_user_id="result-owner",
        ),
    )
    _approve(repo, repo.get_by_uuid_hex(result.object_uuid))
    source_baseline = PerformanceReportService(repo).create_baseline(
        PerformanceReportBaselineCreateRequest(
            name="Render source baseline",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            evidence=[{"object_uuid": result.object_uuid, "object_version": 1}],
            created_by_user_id="per-author",
        )
    )
    report_baseline = PERReportBaselineService(repo).create_baseline(
        PERReportBaselineCreateRequest(
            name="Render report baseline",
            performance_baseline_uuid=source_baseline.baseline_uuid,
            ai_draft_blocks=[
                {
                    "block_id": "ai-render-summary",
                    "section_type": "clinical_performance",
                    "text": ai_text,
                    "model_id": "external-render-model-v1",
                    "source_refs": [
                        {"object_uuid": result.object_uuid, "object_version": 1}
                    ],
                }
            ],
            created_by_user_id="report-author",
        )
    )
    return product, claim, study, result, report_baseline


def _artifacts(repo):
    return list(repo.session.execute(select(GeneratedArtifact)).scalars().all())


def test_side_effect_free_draft_builder_creates_no_artifact(repo):
    *_, baseline = _report_baseline(repo)

    draft = PERDraftService(repo).build_draft(baseline.baseline_uuid)

    assert draft.schema_version == "per-draft-1.2"
    assert _artifacts(repo) == []


@pytest.mark.parametrize(
    ("render_format", "prefix"),
    [("html", b"<!doctype html>"), ("docx", b"PK"), ("pdf", b"%PDF-1.4")],
)
def test_render_formats_are_valid_and_persist_single_artifact(
    repo,
    render_format,
    prefix,
):
    *_, baseline = _report_baseline(repo)

    rendered = PERRenderService(repo).render(
        baseline.baseline_uuid,
        render_format,
        "report-generator",
    )

    assert rendered.content.startswith(prefix)
    assert rendered.checksum_sha256 == hashlib.sha256(rendered.content).hexdigest()
    assert rendered.filename.endswith(f".{render_format}")
    artifacts = _artifacts(repo)
    assert len(artifacts) == 1
    assert artifacts[0].artifact_type == "per_report"
    assert artifacts[0].format == render_format
    assert artifacts[0].checksum == rendered.checksum_sha256
    events = list(
        repo.session.execute(
            select(EventLog).where(EventLog.event_type == "artifact_generated")
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].event_data["artifact_uuid"] == rendered.artifact_uuid
    assert events[0].event_data["format"] == render_format
    assert events[0].event_data["checksum"] == rendered.checksum_sha256

    if render_format == "html":
        text = rendered.content.decode("utf-8")
        assert "Content Provenance" in text
        assert "Completeness Report" in text
        assert "Traceability Appendix" in text
        assert "AI clinical summary." in text
    elif render_format == "docx":
        with zipfile.ZipFile(io.BytesIO(rendered.content)) as archive:
            assert archive.namelist() == [
                "[Content_Types].xml",
                "_rels/.rels",
                "word/document.xml",
                "word/_rels/document.xml.rels",
            ]
            document = archive.read("word/document.xml").decode("utf-8")
            assert "Performance Evaluation Report" in document
            assert "AI clinical summary." in document


def test_repeated_render_is_byte_identical_without_intermediate_draft_artifacts(repo):
    *_, baseline = _report_baseline(repo)
    service = PERRenderService(repo)

    first = service.render(baseline.baseline_uuid, "docx", "report-generator")
    second = service.render(baseline.baseline_uuid, "docx", "report-generator")

    assert first.content == second.content
    assert first.checksum_sha256 == second.checksum_sha256
    assert first.artifact_uuid != second.artifact_uuid
    artifacts = _artifacts(repo)
    assert len(artifacts) == 2
    assert {artifact.artifact_type for artifact in artifacts} == {"per_report"}


def test_render_is_stable_after_live_result_version_changes(repo):
    _, _, _, result, baseline = _report_baseline(repo)
    service = PERRenderService(repo)
    first = service.render(baseline.baseline_uuid, "html", "report-generator")

    result_object = repo.get_by_uuid_hex(result.object_uuid)
    repo.create_version(
        result_object.object_uuid,
        {
            **result.payload.model_dump(mode="json"),
            "interpretation": "Changed after report baseline freeze.",
        },
        "result-owner",
    )
    repo.session.commit()

    second = service.render(baseline.baseline_uuid, "html", "report-generator")

    assert first.content == second.content
    assert first.checksum_sha256 == second.checksum_sha256
    assert b"Changed after report baseline freeze" not in second.content


def test_pdf_rejects_non_winansi_text_without_persisting_artifact(repo):
    *_, baseline = _report_baseline(repo, ai_text="AI summary with snowman \u2603.")

    with pytest.raises(BaselineValidationError, match="WinAnsi"):
        PERRenderService(repo).render(
            baseline.baseline_uuid,
            "pdf",
            "report-generator",
        )

    assert _artifacts(repo) == []


def test_unsupported_render_format_is_rejected(repo):
    *_, baseline = _report_baseline(repo)

    with pytest.raises(BaselineValidationError, match="Unsupported PER render format"):
        PERRenderService(repo).render(
            baseline.baseline_uuid,
            "rtf",
            "report-generator",
        )

    assert _artifacts(repo) == []

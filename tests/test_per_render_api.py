"""API regressions for deterministic PER document downloads."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orkp.api.main import create_app
from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.per_content_models import PERReportBaselineCreateRequest
from orkp.domain.per_report_baseline_service import PERReportBaselineService
from orkp.domain.performance_models import PerformanceStudyCreateRequest
from orkp.domain.performance_report_models import PerformanceReportBaselineCreateRequest
from orkp.domain.performance_report_service import PerformanceReportService
from orkp.domain.performance_result_models import PerformanceResultCreateRequest
from orkp.domain.performance_result_service import PerformanceResultService
from orkp.domain.performance_service import PerformanceStudyService


@pytest.fixture
def api_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return TestClient(
        create_app(session_factory_override=session_factory)
    ), session_factory


def _approve(repo, obj):
    repo.transition_state(obj.object_uuid, "in_review", "author")
    repo.transition_state(obj.object_uuid, "approved", "approver")
    repo.session.commit()
    return obj


def _prepared_report_baseline(session_factory):
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        product, _ = repo.create_object(
            "product",
            {"product_id": "P-RENDER-API", "name": "Render API Product"},
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
                "wording": "Clinical render API claim",
                "regulatory_scope": [],
            },
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
                study_id="ST-RENDER-API",
                study_type="clinical",
                title="Clinical render API study",
                product={"object_uuid": product.uuid_hex, "object_version": 1},
                study_status="completed",
                owner_user_id="study-owner",
            ),
        )
        result = PerformanceResultService(repo).create_result(
            study.object_uuid,
            PerformanceResultCreateRequest(
                result_id="R-RENDER-API",
                study={"object_uuid": study.object_uuid, "object_version": 1},
                claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
                parameter="clinical sensitivity",
                result_value="99.4",
                interpretation="Approved API render interpretation.",
                quality_rating="high",
                owner_user_id="result-owner",
            ),
        )
        _approve(repo, repo.get_by_uuid_hex(result.object_uuid))
        source_baseline = PerformanceReportService(repo).create_baseline(
            PerformanceReportBaselineCreateRequest(
                name="Render API source baseline",
                product={"object_uuid": product.uuid_hex, "object_version": 1},
                evidence=[{"object_uuid": result.object_uuid, "object_version": 1}],
                created_by_user_id="per-author",
            )
        )
        report_baseline = PERReportBaselineService(repo).create_baseline(
            PERReportBaselineCreateRequest(
                name="Render API report baseline",
                performance_baseline_uuid=source_baseline.baseline_uuid,
                created_by_user_id="report-author",
            )
        )
        return report_baseline.baseline_uuid


@pytest.mark.parametrize(
    ("render_format", "prefix", "content_type"),
    [
        ("html", b"<!doctype html>", "text/html"),
        (
            "docx",
            b"PK",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("pdf", b"%PDF-1.4", "application/pdf"),
    ],
)
def test_api_returns_rendered_per_bytes_and_artifact_headers(
    api_context,
    render_format,
    prefix,
    content_type,
):
    client, session_factory = api_context
    baseline_uuid = _prepared_report_baseline(session_factory)

    response = client.post(
        f"/api/v1/per-reports/{baseline_uuid}/renders/{render_format}",
        json={"generated_by_user_id": "report-generator"},
    )

    assert response.status_code == 201
    assert response.content.startswith(prefix)
    assert response.headers["content-type"].startswith(content_type)
    assert response.headers["content-disposition"].endswith(
        f'filename="per-{baseline_uuid[:8]}.{render_format}"'
    )
    assert len(response.headers["x-artifact-uuid"]) == 32
    assert response.headers["x-baseline-uuid"] == baseline_uuid
    assert len(response.headers["x-checksum-sha256"]) == 64


def test_api_rejects_unsupported_per_render_format(api_context):
    client, session_factory = api_context
    baseline_uuid = _prepared_report_baseline(session_factory)

    response = client.post(
        f"/api/v1/per-reports/{baseline_uuid}/renders/rtf",
        json={"generated_by_user_id": "report-generator"},
    )

    assert response.status_code == 422

"""API regressions for reproducible PER draft generation."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orkp.api.main import create_app
from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
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


def _prepared_baseline(session_factory):
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        product, _ = repo.create_object(
            "product",
            {"product_id": "P-PER-API", "name": "PER API Product"},
            "owner",
            "owner",
        )
        _approve(repo, product)
        claim, _ = repo.create_object(
            "claim",
            {"claim_id": "C-PER-API", "wording": "Analytical performance claim"},
            "owner",
            "owner",
        )
        _approve(repo, claim)
        study = PerformanceStudyService(repo).create_study(
            product.uuid_hex,
            PerformanceStudyCreateRequest(
                study_id="ST-PER-API",
                study_type="analytical",
                title="Analytical PER API study",
                product={"object_uuid": product.uuid_hex, "object_version": 1},
                study_status="completed",
                owner_user_id="study-owner",
            ),
        )
        result = PerformanceResultService(repo).create_result(
            study.object_uuid,
            PerformanceResultCreateRequest(
                result_id="R-PER-API",
                study={"object_uuid": study.object_uuid, "object_version": 1},
                claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
                parameter="analytical specificity",
                result_value="99.2",
                quality_rating="high",
                owner_user_id="result-owner",
            ),
        )
        result_obj = repo.get_by_uuid_hex(result.object_uuid)
        _approve(repo, result_obj)
        baseline = PerformanceReportService(repo).create_baseline(
            PerformanceReportBaselineCreateRequest(
                name="PER API draft baseline",
                product={"object_uuid": product.uuid_hex, "object_version": 1},
                evidence=[{"object_uuid": result.object_uuid, "object_version": 1}],
                created_by_user_id="per-author",
            )
        )
        return baseline.baseline_uuid, result.object_uuid


def test_api_generates_per_draft_from_frozen_baseline(api_context):
    client, session_factory = api_context
    baseline_uuid, result_uuid = _prepared_baseline(session_factory)

    response = client.post(
        f"/api/v1/per-reports/{baseline_uuid}/drafts",
        json={"generated_by_user_id": "report-generator"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["baseline_uuid"] == baseline_uuid
    assert body["draft"]["schema_version"] == "per-draft-1.0"
    assert body["draft"]["performance_sections"]["sections"][0]["section_type"] == (
        "analytical_performance"
    )
    assert body["draft"]["traceability_appendix"][0]["performance_result"][
        "object_uuid"
    ] == result_uuid


def test_api_returns_404_for_missing_per_baseline(api_context):
    client, _ = api_context

    response = client.post(
        "/api/v1/per-reports/00000000000000000000000000000001/drafts",
        json={"generated_by_user_id": "report-generator"},
    )

    assert response.status_code == 404

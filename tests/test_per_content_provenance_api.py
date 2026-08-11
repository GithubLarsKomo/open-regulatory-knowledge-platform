"""API regressions for REP-PER-0003 content provenance."""

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


def _prepared_source_baseline(session_factory):
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        product, _ = repo.create_object(
            "product",
            {"product_id": "P-PROV-API", "name": "PER provenance API product"},
            "owner",
            "owner",
        )
        _approve(repo, product)
        claim, _ = repo.create_object(
            "claim",
            {"claim_id": "C-PROV-API", "wording": "Clinical performance claim"},
            "owner",
            "owner",
        )
        _approve(repo, claim)
        study = PerformanceStudyService(repo).create_study(
            product.uuid_hex,
            PerformanceStudyCreateRequest(
                study_id="ST-PROV-API",
                study_type="clinical",
                title="Clinical provenance API study",
                product={"object_uuid": product.uuid_hex, "object_version": 1},
                study_status="completed",
                owner_user_id="study-owner",
            ),
        )
        result = PerformanceResultService(repo).create_result(
            study.object_uuid,
            PerformanceResultCreateRequest(
                result_id="R-PROV-API",
                study={"object_uuid": study.object_uuid, "object_version": 1},
                claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
                parameter="clinical sensitivity",
                result_value="98.8",
                interpretation="Approved API interpretation.",
                quality_rating="high",
                owner_user_id="result-owner",
            ),
        )
        _approve(repo, repo.get_by_uuid_hex(result.object_uuid))
        baseline = PerformanceReportService(repo).create_baseline(
            PerformanceReportBaselineCreateRequest(
                name="API Performance source baseline",
                product={"object_uuid": product.uuid_hex, "object_version": 1},
                evidence=[{"object_uuid": result.object_uuid, "object_version": 1}],
                created_by_user_id="per-author",
            )
        )
        unrelated, _ = repo.create_object(
            "evidence",
            {"evidence_type": "literature", "title": "Unfrozen API evidence"},
            "owner",
            "owner",
        )
        repo.session.commit()
        return baseline.baseline_uuid, result.object_uuid, unrelated.uuid_hex


def _baseline_body(source_baseline_uuid: str, result_uuid: str):
    return {
        "name": "API PER authoring baseline",
        "performance_baseline_uuid": source_baseline_uuid,
        "ai_draft_blocks": [
            {
                "block_id": "ai-api-summary",
                "section_type": "clinical_performance",
                "text": "AI API narrative.",
                "model_id": "external-api-model-v1",
                "source_refs": [{"object_uuid": result_uuid, "object_version": 1}],
            }
        ],
        "created_by_user_id": "report-author",
    }


def test_api_freezes_ai_content_then_generates_provenance_marked_draft(api_context):
    client, session_factory = api_context
    source_baseline_uuid, result_uuid, _ = _prepared_source_baseline(session_factory)

    baseline_response = client.post(
        "/api/v1/per-reports/baselines",
        json=_baseline_body(source_baseline_uuid, result_uuid),
    )

    assert baseline_response.status_code == 201
    baseline_body = baseline_response.json()
    assert baseline_body["source_performance_baseline_uuid"] == source_baseline_uuid
    assert baseline_body["ai_draft_block_count"] == 1
    assert baseline_body["completeness_snapshot_ref"]["object_version"] == 1
    assert baseline_body["section_coverage_snapshot_ref"]["object_version"] == 1

    draft_response = client.post(
        f"/api/v1/per-reports/{baseline_body['baseline_uuid']}/drafts",
        json={"generated_by_user_id": "report-generator"},
    )

    assert draft_response.status_code == 201
    draft = draft_response.json()["draft"]
    assert draft["schema_version"] == "per-draft-1.3"
    assert draft["completeness_report"] is not None
    assert draft["section_coverage"] is not None
    assert len(draft["section_coverage"]["sections"]) == 10
    assert [block["origin"] for block in draft["content_blocks"]] == [
        "approved_source",
        "ai_draft",
    ]
    assert [block["review_status"] for block in draft["content_blocks"]] == [
        "source_approved",
        "unapproved_draft",
    ]
    assert draft["content_blocks"][1]["model_id"] == "external-api-model-v1"


def test_api_rejects_ai_source_not_in_performance_baseline(api_context):
    client, session_factory = api_context
    source_baseline_uuid, result_uuid, unrelated_uuid = _prepared_source_baseline(
        session_factory
    )
    body = _baseline_body(source_baseline_uuid, result_uuid)
    body["ai_draft_blocks"][0]["source_refs"] = [
        {"object_uuid": unrelated_uuid, "object_version": 1}
    ]

    response = client.post("/api/v1/per-reports/baselines", json=body)

    assert response.status_code == 422


def test_api_rejects_duplicate_ai_block_ids(api_context):
    client, session_factory = api_context
    source_baseline_uuid, result_uuid, _ = _prepared_source_baseline(session_factory)
    body = _baseline_body(source_baseline_uuid, result_uuid)
    body["ai_draft_blocks"].append(dict(body["ai_draft_blocks"][0]))

    response = client.post("/api/v1/per-reports/baselines", json=body)

    assert response.status_code == 422


def test_draft_generation_endpoint_rejects_transient_ai_content(api_context):
    client, session_factory = api_context
    source_baseline_uuid, result_uuid, _ = _prepared_source_baseline(session_factory)

    response = client.post(
        f"/api/v1/per-reports/{source_baseline_uuid}/drafts",
        json={
            "generated_by_user_id": "report-generator",
            "ai_draft_blocks": _baseline_body(source_baseline_uuid, result_uuid)[
                "ai_draft_blocks"
            ],
        },
    )

    assert response.status_code == 422

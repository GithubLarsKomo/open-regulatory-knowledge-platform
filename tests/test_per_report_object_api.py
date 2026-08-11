"""API regressions for persisted PER report aggregates and lifecycle."""

import hashlib

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


def _prepared_baselines(session_factory):
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        product, _ = repo.create_object(
            "product",
            {"product_id": "P-REPORT-API", "name": "Persisted PER API Product"},
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
                "wording": "Persisted API clinical claim",
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
                study_id="ST-REPORT-API",
                study_type="clinical",
                title="Persisted PER API study",
                product={"object_uuid": product.uuid_hex, "object_version": 1},
                study_status="completed",
                owner_user_id="study-owner",
            ),
        )
        result = PerformanceResultService(repo).create_result(
            study.object_uuid,
            PerformanceResultCreateRequest(
                result_id="R-REPORT-API",
                study={"object_uuid": study.object_uuid, "object_version": 1},
                claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
                parameter="clinical sensitivity",
                result_value="99.7",
                interpretation="Persisted API interpretation.",
                quality_rating="high",
                owner_user_id="result-owner",
            ),
        )
        _approve(repo, repo.get_by_uuid_hex(result.object_uuid))
        source_baseline = PerformanceReportService(repo).create_baseline(
            PerformanceReportBaselineCreateRequest(
                name="Persisted API source baseline",
                product={"object_uuid": product.uuid_hex, "object_version": 1},
                evidence=[{"object_uuid": result.object_uuid, "object_version": 1}],
                created_by_user_id="per-author",
            )
        )
        report_baseline = PERReportBaselineService(repo).create_baseline(
            PERReportBaselineCreateRequest(
                name="Persisted API report baseline",
                performance_baseline_uuid=source_baseline.baseline_uuid,
                created_by_user_id="report-author",
            )
        )
        second_report_baseline = PERReportBaselineService(repo).create_baseline(
            PERReportBaselineCreateRequest(
                name="Persisted API successor baseline",
                performance_baseline_uuid=source_baseline.baseline_uuid,
                created_by_user_id="report-author",
            )
        )
        return (
            product.uuid_hex,
            source_baseline.baseline_uuid,
            report_baseline.baseline_uuid,
            second_report_baseline.baseline_uuid,
        )


def _create(client, product_uuid: str, baseline_uuid: str, report_type="PER"):
    return client.post(
        "/api/v1/per-reports",
        json={
            "product_uuid": product_uuid,
            "baseline_uuid": baseline_uuid,
            "report_type": report_type,
            "owner_user_id": "report-owner",
        },
    )


def test_api_creates_gets_and_returns_canonical_persisted_report(api_context):
    client, session_factory = api_context
    product_uuid, _, report_baseline_uuid, _ = _prepared_baselines(session_factory)

    created = _create(client, product_uuid, report_baseline_uuid, "PER-addendum")
    assert created.status_code == 201
    body = created.json()
    report_uuid = body["report_uuid"]
    assert body["object_version"] == 1
    assert body["lifecycle_state"] == "draft"
    assert body["report_type"] == "PER-addendum"
    assert body["baseline_uuid"] == report_baseline_uuid

    fetched = client.get(f"/api/v1/per-reports/{report_uuid}")
    assert fetched.status_code == 200
    assert fetched.json() == body

    canonical = client.get(f"/api/v1/per-reports/{report_uuid}/canonical-json")
    assert canonical.status_code == 200
    canonical_body = canonical.json()
    assert canonical_body["report_uuid"] == report_uuid
    assert canonical_body["canonical_checksum_sha256"] == hashlib.sha256(
        canonical_body["canonical_json"].encode("utf-8")
    ).hexdigest()


def test_api_rejects_raw_performance_baseline_and_invalid_report_type(api_context):
    client, session_factory = api_context
    product_uuid, source_baseline_uuid, _, _ = _prepared_baselines(session_factory)

    raw = _create(client, product_uuid, source_baseline_uuid)
    assert raw.status_code == 422

    invalid_type = _create(client, product_uuid, source_baseline_uuid, "CER")
    assert invalid_type.status_code == 422


def test_api_submit_approval_requires_independent_approver(api_context):
    client, session_factory = api_context
    product_uuid, _, report_baseline_uuid, _ = _prepared_baselines(session_factory)
    report_uuid = _create(client, product_uuid, report_baseline_uuid).json()["report_uuid"]

    submitted = client.post(
        f"/api/v1/per-reports/{report_uuid}/submit",
        json={"actor_user_id": "report-owner"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["lifecycle_state"] == "in_review"

    self_approval = client.post(
        f"/api/v1/per-reports/{report_uuid}/approve",
        json={"actor_user_id": "report-owner"},
    )
    assert self_approval.status_code == 403

    approved = client.post(
        f"/api/v1/per-reports/{report_uuid}/approve",
        json={"actor_user_id": "independent-approver", "comments": "Reviewed"},
    )
    assert approved.status_code == 200
    assert approved.json()["lifecycle_state"] == "approved"


def test_api_regeneration_after_approval_creates_successor_aggregate(api_context):
    client, session_factory = api_context
    product_uuid, _, report_baseline_uuid, successor_baseline_uuid = _prepared_baselines(
        session_factory
    )
    report_uuid = _create(client, product_uuid, report_baseline_uuid).json()["report_uuid"]
    client.post(
        f"/api/v1/per-reports/{report_uuid}/submit",
        json={"actor_user_id": "report-owner"},
    )
    client.post(
        f"/api/v1/per-reports/{report_uuid}/approve",
        json={"actor_user_id": "independent-approver"},
    )

    regenerated = client.post(
        f"/api/v1/per-reports/{report_uuid}/regenerate",
        json={
            "baseline_uuid": successor_baseline_uuid,
            "actor_user_id": "successor-owner",
        },
    )

    assert regenerated.status_code == 201
    body = regenerated.json()
    assert body["report_uuid"] != report_uuid
    assert body["object_version"] == 1
    assert body["lifecycle_state"] == "draft"
    assert body["predecessor_report"] == {
        "object_uuid": report_uuid,
        "object_version": 1,
    }

"""API regressions for reproducible Performance Evaluation sections."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orkp.api.main import create_app
from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.performance_models import PerformanceStudyCreateRequest
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


def _prepared_context(session_factory, approve_result=True):
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        product, _ = repo.create_object(
            "product",
            {"product_id": "P-API", "name": "PER API Product"},
            "owner",
            "owner",
        )
        _approve(repo, product)
        claim, _ = repo.create_object(
            "claim",
            {"claim_id": "C-API", "wording": "Clinical performance claim"},
            "owner",
            "owner",
        )
        _approve(repo, claim)
        study = PerformanceStudyService(repo).create_study(
            product.uuid_hex,
            PerformanceStudyCreateRequest(
                study_id="ST-API",
                study_type="clinical",
                title="Clinical performance study",
                product={"object_uuid": product.uuid_hex, "object_version": 1},
                study_status="completed",
                owner_user_id="study-owner",
            ),
        )
        result = PerformanceResultService(repo).create_result(
            study.object_uuid,
            PerformanceResultCreateRequest(
                result_id="R-API",
                study={"object_uuid": study.object_uuid, "object_version": 1},
                claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
                parameter="clinical sensitivity",
                result_value="97.4",
                quality_rating="high",
                owner_user_id="result-owner",
            ),
        )
        result_obj = repo.get_by_uuid_hex(result.object_uuid)
        if approve_result:
            _approve(repo, result_obj)
        return product.uuid_hex, result.object_uuid


def test_api_creates_reads_and_generates_per_sections(api_context):
    client, session_factory = api_context
    product_uuid, result_uuid = _prepared_context(session_factory)

    created = client.post(
        "/api/v1/performance-report-baselines",
        json={
            "name": "PER API baseline",
            "product": {"object_uuid": product_uuid, "object_version": 1},
            "evidence": [{"object_uuid": result_uuid, "object_version": 1}],
            "created_by_user_id": "per-author",
        },
    )
    assert created.status_code == 201
    baseline = created.json()
    assert baseline["evidence_count"] == 1
    assert baseline["item_count"] == 4

    loaded = client.get(
        f"/api/v1/performance-report-baselines/{baseline['baseline_uuid']}"
    )
    assert loaded.status_code == 200
    assert loaded.json() == baseline

    generated = client.post(
        f"/api/v1/performance-report-baselines/{baseline['baseline_uuid']}/sections",
        json={"generated_by_user_id": "per-generator"},
    )
    assert generated.status_code == 201
    body = generated.json()
    assert body["report"]["schema_version"] == "per-sections-1.0"
    assert [section["section_type"] for section in body["report"]["sections"]] == [
        "clinical_performance"
    ]
    assert (
        body["report"]["sections"][0]["items"][0]["performance_result"]["object_uuid"]
        == result_uuid
    )


def test_api_rejects_draft_performance_result_in_baseline(api_context):
    client, session_factory = api_context
    product_uuid, result_uuid = _prepared_context(session_factory, approve_result=False)

    response = client.post(
        "/api/v1/performance-report-baselines",
        json={
            "name": "Invalid PER baseline",
            "product": {"object_uuid": product_uuid, "object_version": 1},
            "evidence": [{"object_uuid": result_uuid, "object_version": 1}],
            "created_by_user_id": "per-author",
        },
    )

    assert response.status_code == 409
    assert "state 'draft'" in response.json()["detail"]

"""Regression for generic-object bypass of canonical PER cross-domain provenance."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import BaselineValidationError
from orkp.domain.per_content_models import PERReportBaselineCreateRequest
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


def test_approved_benefit_risk_without_canonical_relations_is_rejected(repo):
    product, _ = repo.create_object(
        "product",
        {"product_id": "P-BYPASS", "name": "Bypass Product"},
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
            "wording": "Bypass clinical claim",
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
            study_id="ST-BYPASS",
            study_type="clinical",
            title="Bypass study",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            study_status="completed",
            owner_user_id="study-owner",
        ),
    )
    result = PerformanceResultService(repo).create_result(
        study.object_uuid,
        PerformanceResultCreateRequest(
            result_id="R-BYPASS",
            study={"object_uuid": study.object_uuid, "object_version": 1},
            claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
            parameter="clinical sensitivity",
            result_value="99.9",
            quality_rating="high",
            owner_user_id="result-owner",
        ),
    )
    _approve(repo, repo.get_by_uuid_hex(result.object_uuid))
    source_baseline = PerformanceReportService(repo).create_baseline(
        PerformanceReportBaselineCreateRequest(
            name="Bypass source baseline",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            evidence=[{"object_uuid": result.object_uuid, "object_version": 1}],
            created_by_user_id="per-author",
        )
    )

    risk, _ = repo.create_object(
        "risk_analysis",
        {"risk_id": "RA-BYPASS"},
        "risk-owner",
        "risk-owner",
    )
    repo.create_relation(
        source_uuid=risk.object_uuid,
        source_version=1,
        target_uuid=product.object_uuid,
        target_version=1,
        relation_type="applies_to_product",
        created_by="risk-owner",
    )
    residual, _ = repo.create_object(
        "residual_risk_evaluation",
        {"residual_id": "RR-BYPASS"},
        "risk-owner",
        "risk-owner",
    )
    policy, _ = repo.create_object(
        "risk_policy",
        {"policy_id": "RP-BYPASS"},
        "risk-owner",
        "risk-owner",
    )
    fake_benefit, _ = repo.create_object(
        "benefit_risk",
        {
            "analysis_id": "BR-BYPASS",
            "residual_evaluation": {
                "object_uuid": residual.uuid_hex,
                "object_version": 1,
            },
            "risk_analysis": {"object_uuid": risk.uuid_hex, "object_version": 1},
            "risk_policy": {"object_uuid": policy.uuid_hex, "object_version": 1},
            "benefits": "Benefit",
            "residual_risks": "Residual risk",
            "rationale": "Favorable",
            "conclusion": "favorable",
            "evaluator_user_id": "risk-author",
            "evaluated_at": "2026-08-11T00:00:00+00:00",
        },
        "risk-author",
        "risk-author",
    )
    _approve(repo, fake_benefit, actor="risk-approver")

    with pytest.raises(BaselineValidationError, match="benefit_risk_for"):
        PERReportBaselineService(repo).create_baseline(
            PERReportBaselineCreateRequest(
                name="Bypass report baseline",
                performance_baseline_uuid=source_baseline.baseline_uuid,
                benefit_risk_sources=[
                    {"object_uuid": fake_benefit.uuid_hex, "object_version": 1}
                ],
                created_by_user_id="report-author",
            )
        )

    assert repo.list_objects(object_type="report_completeness") == []
    assert repo.list_objects(object_type="report_section_coverage") == []

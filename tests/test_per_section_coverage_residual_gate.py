"""Regressions for Benefit-Risk residual provenance in PER section coverage."""

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


def _performance_context(repo):
    product, _ = repo.create_object(
        "product",
        {"product_id": "P-RES-GATE", "name": "Residual Gate Product"},
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
            "wording": "Residual gate clinical claim",
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
            study_id="ST-RES-GATE",
            study_type="clinical",
            title="Residual gate study",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            study_status="completed",
            owner_user_id="study-owner",
        ),
    )
    result = PerformanceResultService(repo).create_result(
        study.object_uuid,
        PerformanceResultCreateRequest(
            result_id="R-RES-GATE",
            study={"object_uuid": study.object_uuid, "object_version": 1},
            claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
            parameter="clinical sensitivity",
            result_value="99.7",
            quality_rating="high",
            owner_user_id="result-owner",
        ),
    )
    _approve(repo, repo.get_by_uuid_hex(result.object_uuid))
    baseline = PerformanceReportService(repo).create_baseline(
        PerformanceReportBaselineCreateRequest(
            name="Residual gate source baseline",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            evidence=[{"object_uuid": result.object_uuid, "object_version": 1}],
            created_by_user_id="per-author",
        )
    )
    return product, baseline


def _residual_payload(
    risk_uuid: str,
    policy_uuid: str,
    *,
    acceptable: bool = False,
    benefit_risk_required: bool = True,
):
    return {
        "evaluation_id": "RRE-RES-GATE",
        "risk_analysis_uuid": risk_uuid,
        "risk_analysis_version": 1,
        "initial_evaluation_uuid": risk_uuid,
        "initial_evaluation_version": 1,
        "control_verifications": [
            {"object_uuid": risk_uuid, "object_version": 1}
        ],
        "residual_severity": "moderate",
        "residual_probability": "possible",
        "calculated_risk_level": "high",
        "acceptable": acceptable,
        "action_required": "benefit_risk_required",
        "severity_improved": False,
        "probability_improved": False,
        "severity_worsened": False,
        "probability_worsened": False,
        "risk_level_improved": False,
        "reduced": False,
        "regression_detected": False,
        "benefit_risk_required": benefit_risk_required,
        "risk_policy_uuid": policy_uuid,
        "risk_policy_version": 1,
        "policy_revision": "1.0",
        "evaluator_user_id": "risk-author",
        "rationale": "Residual context for provenance test",
        "evaluated_at": "2026-08-11T00:00:00+00:00",
    }


def _benefit_payload(residual_uuid: str, risk_uuid: str, policy_uuid: str):
    return {
        "analysis_id": "BR-RES-GATE",
        "residual_evaluation": {
            "object_uuid": residual_uuid,
            "object_version": 1,
        },
        "risk_analysis": {"object_uuid": risk_uuid, "object_version": 1},
        "risk_policy": {"object_uuid": policy_uuid, "object_version": 1},
        "benefits": "Benefit",
        "residual_risks": "Residual risk",
        "rationale": "Benefit outweighs risk",
        "conclusion": "favorable",
        "evaluator_user_id": "risk-author",
        "evaluated_at": "2026-08-11T00:00:00+00:00",
    }


def _link_risk_to_product(repo, risk, product):
    repo.create_relation(
        source_uuid=risk.object_uuid,
        source_version=1,
        target_uuid=product.object_uuid,
        target_version=1,
        relation_type="applies_to_product",
        created_by="risk-owner",
    )


def _link_residual_context(repo, residual, risk, policy):
    repo.create_relation(
        source_uuid=residual.object_uuid,
        source_version=1,
        target_uuid=risk.object_uuid,
        target_version=1,
        relation_type="residual_of",
        created_by="risk-owner",
    )
    repo.create_relation(
        source_uuid=residual.object_uuid,
        source_version=1,
        target_uuid=policy.object_uuid,
        target_version=1,
        relation_type="uses_risk_policy",
        created_by="risk-owner",
    )


def _link_benefit_context(repo, benefit, residual, policy):
    repo.create_relation(
        source_uuid=benefit.object_uuid,
        source_version=1,
        target_uuid=residual.object_uuid,
        target_version=1,
        relation_type="benefit_risk_for",
        created_by="risk-author",
    )
    repo.create_relation(
        source_uuid=benefit.object_uuid,
        source_version=1,
        target_uuid=policy.object_uuid,
        target_version=1,
        relation_type="uses_risk_policy",
        created_by="risk-author",
    )


def _freeze(repo, source_baseline_uuid: str, benefit_uuid: str):
    return PERReportBaselineService(repo).create_baseline(
        PERReportBaselineCreateRequest(
            name="Residual provenance report baseline",
            performance_baseline_uuid=source_baseline_uuid,
            benefit_risk_sources=[
                {"object_uuid": benefit_uuid, "object_version": 1}
            ],
            created_by_user_id="report-author",
        )
    )


def test_benefit_risk_rejects_residual_from_different_risk_analysis(repo):
    product, source = _performance_context(repo)
    report_risk, _ = repo.create_object(
        "risk_analysis", {"risk_id": "RA-REPORT"}, "risk-owner", "risk-owner"
    )
    residual_risk, _ = repo.create_object(
        "risk_analysis", {"risk_id": "RA-RESIDUAL"}, "risk-owner", "risk-owner"
    )
    policy, _ = repo.create_object(
        "risk_policy", {"policy_id": "RP-RES-GATE"}, "risk-owner", "risk-owner"
    )
    _link_risk_to_product(repo, report_risk, product)
    residual, _ = repo.create_object(
        "residual_risk_evaluation",
        _residual_payload(residual_risk.uuid_hex, policy.uuid_hex),
        "risk-owner",
        "risk-owner",
    )
    _link_residual_context(repo, residual, residual_risk, policy)
    benefit, _ = repo.create_object(
        "benefit_risk",
        _benefit_payload(residual.uuid_hex, report_risk.uuid_hex, policy.uuid_hex),
        "risk-author",
        "risk-author",
    )
    _link_benefit_context(repo, benefit, residual, policy)
    _approve(repo, benefit, actor="risk-approver")

    with pytest.raises(BaselineValidationError, match="different Risk Analysis"):
        _freeze(repo, source.baseline_uuid, benefit.uuid_hex)

    assert repo.list_objects(object_type="report_completeness") == []
    assert repo.list_objects(object_type="report_section_coverage") == []


@pytest.mark.parametrize(
    ("acceptable", "benefit_risk_required"),
    [(True, True), (False, False)],
)
def test_benefit_risk_rejects_residual_that_does_not_require_analysis(
    repo,
    acceptable,
    benefit_risk_required,
):
    product, source = _performance_context(repo)
    risk, _ = repo.create_object(
        "risk_analysis", {"risk_id": "RA-NOT-REQUIRED"}, "risk-owner", "risk-owner"
    )
    policy, _ = repo.create_object(
        "risk_policy", {"policy_id": "RP-NOT-REQUIRED"}, "risk-owner", "risk-owner"
    )
    _link_risk_to_product(repo, risk, product)
    residual, _ = repo.create_object(
        "residual_risk_evaluation",
        _residual_payload(
            risk.uuid_hex,
            policy.uuid_hex,
            acceptable=acceptable,
            benefit_risk_required=benefit_risk_required,
        ),
        "risk-owner",
        "risk-owner",
    )
    _link_residual_context(repo, residual, risk, policy)
    benefit, _ = repo.create_object(
        "benefit_risk",
        _benefit_payload(residual.uuid_hex, risk.uuid_hex, policy.uuid_hex),
        "risk-author",
        "risk-author",
    )
    _link_benefit_context(repo, benefit, residual, policy)
    _approve(repo, benefit, actor="risk-approver")

    with pytest.raises(BaselineValidationError, match="does not require benefit-risk"):
        _freeze(repo, source.baseline_uuid, benefit.uuid_hex)

    assert repo.list_objects(object_type="report_completeness") == []
    assert repo.list_objects(object_type="report_section_coverage") == []

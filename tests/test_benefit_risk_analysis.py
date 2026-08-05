"""Service tests for version-pinned Benefit-Risk Analysis."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.benefit_risk_models import BenefitRiskAnalysisCreateRequest
from orkp.domain.benefit_risk_service import BenefitRiskAnalysisService
from orkp.domain.exceptions import (
    InvalidRelationError,
    RiskEvaluationError,
    SelfApprovalNotAllowedError,
)


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _policy_payload():
    severity = ["negligible", "minor", "moderate", "critical", "catastrophic"]
    probability = ["improbable", "unlikely", "possible", "likely", "probable"]
    return {
        "policy_id": "POL-001",
        "name": "Benefit-Risk Test Policy",
        "policy_version": "1.0",
        "severity_scale": severity,
        "probability_scale": probability,
        "risk_levels": ["low", "medium", "high", "intolerable"],
        "risk_matrix": {
            sev: {prob: "high" for prob in probability} for sev in severity
        },
        "acceptability_rules": {"high": False},
        "required_actions": {"high": "benefit_risk_required"},
        "control_hierarchy": [
            "design_by_safety",
            "protective_measure",
            "information_for_safety",
        ],
        "benefit_risk_required_for": ["high"],
    }


def _context(repo, *, acceptable=False, benefit_risk_required=True):
    risk_analysis, _ = repo.create_object(
        "risk_analysis",
        {"risk_id": "R-1", "title": "Test risk"},
        "owner",
        "owner",
    )
    risk_policy, _ = repo.create_object(
        "risk_policy",
        _policy_payload(),
        "owner",
        "owner",
    )
    repo.transition_state(risk_policy.object_uuid, "in_review", "owner")
    repo.transition_state(risk_policy.object_uuid, "approved", "approver")
    repo.transition_state(risk_policy.object_uuid, "effective", "owner")

    residual_payload = {
        "evaluation_id": "rre-test",
        "risk_analysis_uuid": risk_analysis.uuid_hex,
        "risk_analysis_version": 1,
        "initial_evaluation_uuid": uuid4().hex,
        "initial_evaluation_version": 1,
        "control_verifications": [
            {"object_uuid": uuid4().hex, "object_version": 1}
        ],
        "residual_severity": "critical",
        "residual_probability": "possible",
        "calculated_risk_level": "high",
        "acceptable": acceptable,
        "action_required": "benefit_risk_required",
        "severity_improved": False,
        "probability_improved": True,
        "severity_worsened": False,
        "probability_worsened": False,
        "risk_level_improved": True,
        "reduced": True,
        "regression_detected": False,
        "benefit_risk_required": benefit_risk_required,
        "risk_policy_uuid": risk_policy.uuid_hex,
        "risk_policy_version": 1,
        "policy_revision": "1.0",
        "evaluator_user_id": "owner",
        "rationale": "Residual risk remains high.",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
    residual, _ = repo.create_object(
        "residual_risk_evaluation",
        residual_payload,
        "owner",
        "owner",
    )
    repo.create_relation(
        source_uuid=residual.object_uuid,
        source_version=1,
        target_uuid=risk_analysis.object_uuid,
        target_version=1,
        relation_type="residual_of",
        created_by="owner",
    )
    repo.create_relation(
        source_uuid=residual.object_uuid,
        source_version=1,
        target_uuid=risk_policy.object_uuid,
        target_version=1,
        relation_type="uses_risk_policy",
        created_by="owner",
    )
    repo.session.commit()
    return risk_analysis, risk_policy, residual


def _request(risk_analysis, risk_policy, residual, evaluator="reviewer"):
    return BenefitRiskAnalysisCreateRequest(
        residual_evaluation={
            "object_uuid": residual.uuid_hex,
            "object_version": 1,
        },
        risk_analysis={
            "object_uuid": risk_analysis.uuid_hex,
            "object_version": 1,
        },
        risk_policy={
            "object_uuid": risk_policy.uuid_hex,
            "object_version": 1,
        },
        benefits="The intended clinical benefit outweighs the remaining risk.",
        residual_risks="A high residual risk remains after verified controls.",
        rationale="Clinical benefit and available alternatives justify continuation.",
        conclusion="favorable",
        evaluator_user_id=evaluator,
    )


def test_create_benefit_risk_analysis_persists_version_pinned_relations(repo):
    risk_analysis, risk_policy, residual = _context(repo)
    service = BenefitRiskAnalysisService(repo)

    response = service.create_analysis(
        residual.uuid_hex,
        _request(risk_analysis, risk_policy, residual),
    )

    assert response.lifecycle_state == "draft"
    assert response.object_version == 1
    assert response.payload.analysis_id.startswith("bra-")
    relations = repo.list_active_relations_for_source(bytes.fromhex(response.object_uuid))
    assert any(
        relation.relation_type == "benefit_risk_for"
        and relation.target_uuid == residual.object_uuid
        and relation.target_version == 1
        for relation in relations
    )
    assert any(
        relation.relation_type == "uses_risk_policy"
        and relation.target_uuid == risk_policy.object_uuid
        and relation.target_version == 1
        for relation in relations
    )


def test_acceptable_residual_risk_rejects_benefit_risk_analysis(repo):
    risk_analysis, risk_policy, residual = _context(
        repo,
        acceptable=True,
        benefit_risk_required=False,
    )
    with pytest.raises(RiskEvaluationError):
        BenefitRiskAnalysisService(repo).create_analysis(
            residual.uuid_hex,
            _request(risk_analysis, risk_policy, residual),
        )


def test_mismatched_risk_context_is_rejected(repo):
    risk_analysis, risk_policy, residual = _context(repo)
    other_risk, _ = repo.create_object(
        "risk_analysis",
        {"risk_id": "R-2", "title": "Other risk"},
        "owner",
        "owner",
    )
    request = _request(risk_analysis, risk_policy, residual).model_copy(
        update={
            "risk_analysis": {
                "object_uuid": other_risk.uuid_hex,
                "object_version": 1,
            }
        }
    )

    with pytest.raises(InvalidRelationError):
        BenefitRiskAnalysisService(repo).create_analysis(residual.uuid_hex, request)


def test_creator_cannot_approve_own_benefit_risk_analysis(repo):
    risk_analysis, risk_policy, residual = _context(repo)
    service = BenefitRiskAnalysisService(repo)
    response = service.create_analysis(
        residual.uuid_hex,
        _request(risk_analysis, risk_policy, residual, evaluator="reviewer"),
    )
    service.transition_state(response.object_uuid, "in_review", "reviewer")

    with pytest.raises(SelfApprovalNotAllowedError):
        service.transition_state(response.object_uuid, "approved", "reviewer")


def test_independent_approver_can_approve_benefit_risk_analysis(repo):
    risk_analysis, risk_policy, residual = _context(repo)
    service = BenefitRiskAnalysisService(repo)
    response = service.create_analysis(
        residual.uuid_hex,
        _request(risk_analysis, risk_policy, residual, evaluator="reviewer"),
    )
    service.transition_state(response.object_uuid, "in_review", "reviewer")

    approved = service.transition_state(response.object_uuid, "approved", "approver")

    assert approved.lifecycle_state == "approved"
    assert approved.payload.conclusion == "favorable"

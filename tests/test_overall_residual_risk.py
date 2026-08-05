"""Service tests for product-level Overall Residual Risk evaluation."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    InvalidRelationError,
    RiskEvaluationError,
    SelfApprovalNotAllowedError,
)
from orkp.domain.overall_residual_risk_models import OverallResidualRiskCreateRequest
from orkp.domain.overall_residual_risk_service import OverallResidualRiskService


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
        "policy_id": "POL-ORR",
        "name": "Overall Residual Risk Policy",
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


def _residual_payload(risk, policy, *, acceptable):
    return {
        "evaluation_id": f"rre-{uuid4().hex[:8]}",
        "risk_analysis_uuid": risk.uuid_hex,
        "risk_analysis_version": risk.current_version,
        "initial_evaluation_uuid": uuid4().hex,
        "initial_evaluation_version": 1,
        "control_verifications": [{"object_uuid": uuid4().hex, "object_version": 1}],
        "residual_severity": "critical",
        "residual_probability": "possible",
        "calculated_risk_level": "high",
        "acceptable": acceptable,
        "action_required": "none" if acceptable else "benefit_risk_required",
        "severity_improved": False,
        "probability_improved": True,
        "severity_worsened": False,
        "probability_worsened": False,
        "risk_level_improved": True,
        "reduced": True,
        "regression_detected": False,
        "benefit_risk_required": not acceptable,
        "risk_policy_uuid": policy.uuid_hex,
        "risk_policy_version": policy.current_version,
        "policy_revision": "1.0",
        "evaluator_user_id": "risk-evaluator",
        "rationale": "Residual risk assessment.",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def _benefit_payload(risk, policy, residual, *, conclusion="favorable"):
    return {
        "residual_evaluation": {
            "object_uuid": residual.uuid_hex,
            "object_version": residual.current_version,
        },
        "risk_analysis": {
            "object_uuid": risk.uuid_hex,
            "object_version": risk.current_version,
        },
        "risk_policy": {
            "object_uuid": policy.uuid_hex,
            "object_version": policy.current_version,
        },
        "benefits": "The clinical benefit is meaningful.",
        "residual_risks": "A high residual risk remains.",
        "rationale": "Benefit outweighs the remaining risk.",
        "conclusion": conclusion,
        "evaluator_user_id": "benefit-reviewer",
        "analysis_id": f"bra-{uuid4().hex[:8]}",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def _create_approved_risk_with_residual(
    repo,
    product,
    policy,
    *,
    suffix: str,
    acceptable: bool = True,
    has_risk_link: bool = True,
    applies_to_product_link: bool = False,
):
    risk, _ = repo.create_object(
        "risk_analysis",
        {"risk_id": f"R-{suffix}", "title": f"Risk {suffix}"},
        "risk-owner",
        "risk-owner",
    )
    repo.transition_state(risk.object_uuid, "in_review", "risk-owner")
    repo.transition_state(risk.object_uuid, "approved", "risk-approver")

    if has_risk_link:
        repo.create_relation(
            source_uuid=product.object_uuid,
            source_version=product.current_version,
            target_uuid=risk.object_uuid,
            target_version=risk.current_version,
            relation_type="has_risk",
            created_by="product-owner",
        )
    if applies_to_product_link:
        repo.create_relation(
            source_uuid=risk.object_uuid,
            source_version=risk.current_version,
            target_uuid=product.object_uuid,
            target_version=product.current_version,
            relation_type="applies_to_product",
            created_by="risk-owner",
        )

    residual, _ = repo.create_object(
        "residual_risk_evaluation",
        _residual_payload(risk, policy, acceptable=acceptable),
        "risk-evaluator",
        "risk-evaluator",
    )
    repo.create_relation(
        source_uuid=residual.object_uuid,
        source_version=residual.current_version,
        target_uuid=risk.object_uuid,
        target_version=risk.current_version,
        relation_type="residual_of",
        created_by="risk-evaluator",
    )
    repo.create_relation(
        source_uuid=residual.object_uuid,
        source_version=residual.current_version,
        target_uuid=policy.object_uuid,
        target_version=policy.current_version,
        relation_type="uses_risk_policy",
        created_by="risk-evaluator",
    )
    return risk, residual


def _seed_context(
    repo,
    *,
    acceptable=True,
    with_benefit=False,
    has_risk_link=True,
    applies_to_product_link=False,
):
    product, _ = repo.create_object(
        "product",
        {"product_id": "P-ORR", "name": "Overall Risk Product"},
        "product-owner",
        "product-owner",
    )
    policy, _ = repo.create_object(
        "risk_policy",
        _policy_payload(),
        "policy-owner",
        "policy-owner",
    )
    repo.transition_state(policy.object_uuid, "in_review", "policy-owner")
    repo.transition_state(policy.object_uuid, "approved", "policy-approver")
    repo.transition_state(policy.object_uuid, "effective", "policy-owner")

    risk, residual = _create_approved_risk_with_residual(
        repo,
        product,
        policy,
        suffix="ORR",
        acceptable=acceptable,
        has_risk_link=has_risk_link,
        applies_to_product_link=applies_to_product_link,
    )

    benefit = None
    if with_benefit:
        benefit, _ = repo.create_object(
            "benefit_risk",
            _benefit_payload(risk, policy, residual),
            "benefit-reviewer",
            "benefit-reviewer",
        )
        repo.create_relation(
            source_uuid=benefit.object_uuid,
            source_version=benefit.current_version,
            target_uuid=residual.object_uuid,
            target_version=residual.current_version,
            relation_type="benefit_risk_for",
            created_by="benefit-reviewer",
        )
        repo.create_relation(
            source_uuid=benefit.object_uuid,
            source_version=benefit.current_version,
            target_uuid=policy.object_uuid,
            target_version=policy.current_version,
            relation_type="uses_risk_policy",
            created_by="benefit-reviewer",
        )
        repo.transition_state(benefit.object_uuid, "in_review", "benefit-reviewer")
        repo.transition_state(benefit.object_uuid, "approved", "benefit-approver")

    repo.session.commit()
    return product, risk, policy, residual, benefit


def _request(product, evaluator="overall-reviewer"):
    return OverallResidualRiskCreateRequest(
        product={
            "object_uuid": product.uuid_hex,
            "object_version": product.current_version,
        },
        acceptable=True,
        rationale="All product-level residual risks were considered together.",
        evaluator_user_id=evaluator,
    )


def test_create_overall_residual_risk_persists_exact_sources(repo):
    product, risk, policy, residual, _ = _seed_context(repo)

    response = OverallResidualRiskService(repo).create_evaluation(
        product.uuid_hex,
        _request(product),
    )

    assert response.lifecycle_state == "draft"
    assert response.payload.acceptable is True
    assert len(response.payload.entries) == 1
    entry = response.payload.entries[0]
    assert entry.risk_analysis.object_uuid == risk.uuid_hex
    assert entry.residual_evaluation.object_uuid == residual.uuid_hex
    assert entry.risk_policy.object_uuid == policy.uuid_hex

    source = bytes.fromhex(response.object_uuid)
    relations = repo.list_active_relations_for_source(source)
    assert any(
        relation.relation_type == "overall_risk_for"
        and relation.target_uuid == product.object_uuid
        and relation.target_version == product.current_version
        for relation in relations
    )
    assert any(
        relation.relation_type == "aggregates_residual_risk"
        and relation.target_uuid == residual.object_uuid
        and relation.target_version == residual.current_version
        for relation in relations
    )
    assert any(
        relation.relation_type == "uses_risk_policy"
        and relation.target_uuid == policy.object_uuid
        and relation.target_version == policy.current_version
        for relation in relations
    )


def test_product_without_approved_risks_is_rejected(repo):
    product, _ = repo.create_object(
        "product",
        {"product_id": "P-EMPTY", "name": "Empty product"},
        "owner",
        "owner",
    )
    repo.session.commit()

    with pytest.raises(RiskEvaluationError):
        OverallResidualRiskService(repo).create_evaluation(
            product.uuid_hex,
            _request(product),
        )


def test_both_product_risk_link_directions_are_deduplicated(repo):
    product, risk, _, _, _ = _seed_context(
        repo,
        has_risk_link=True,
        applies_to_product_link=True,
    )

    response = OverallResidualRiskService(repo).create_evaluation(
        product.uuid_hex,
        _request(product),
    )

    assert len(response.payload.entries) == 1
    assert response.payload.entries[0].risk_analysis.object_uuid == risk.uuid_hex


def test_applies_to_product_direction_is_supported_without_has_risk(repo):
    product, risk, _, _, _ = _seed_context(
        repo,
        has_risk_link=False,
        applies_to_product_link=True,
    )

    response = OverallResidualRiskService(repo).create_evaluation(
        product.uuid_hex,
        _request(product),
    )

    assert len(response.payload.entries) == 1
    assert response.payload.entries[0].risk_analysis.object_uuid == risk.uuid_hex


def test_all_current_approved_product_risks_are_included(repo):
    product, first_risk, policy, _, _ = _seed_context(repo)
    second_risk, _ = _create_approved_risk_with_residual(
        repo,
        product,
        policy,
        suffix="SECOND",
    )
    repo.session.commit()

    response = OverallResidualRiskService(repo).create_evaluation(
        product.uuid_hex,
        _request(product),
    )

    included = {entry.risk_analysis.object_uuid for entry in response.payload.entries}
    assert included == {first_risk.uuid_hex, second_risk.uuid_hex}


def test_stale_product_risk_relation_is_not_aggregated(repo):
    product, _, _, _, _ = _seed_context(repo)
    repo.create_version(
        product.object_uuid,
        {"product_id": "P-ORR", "name": "Overall Risk Product v2"},
        "product-owner",
    )
    repo.session.commit()

    with pytest.raises(RiskEvaluationError):
        OverallResidualRiskService(repo).create_evaluation(
            product.uuid_hex,
            _request(product),
        )


def test_unacceptable_residual_requires_favorable_benefit_risk(repo):
    product, _, _, _, _ = _seed_context(repo, acceptable=False)

    with pytest.raises(RiskEvaluationError):
        OverallResidualRiskService(repo).create_evaluation(
            product.uuid_hex,
            _request(product),
        )


def test_favorable_benefit_risk_is_pinned_and_related(repo):
    product, _, _, _, benefit = _seed_context(
        repo,
        acceptable=False,
        with_benefit=True,
    )

    response = OverallResidualRiskService(repo).create_evaluation(
        product.uuid_hex,
        _request(product),
    )

    entry = response.payload.entries[0]
    assert [reference.object_uuid for reference in entry.benefit_risk_analyses] == [
        benefit.uuid_hex
    ]
    relations = repo.list_active_relations_for_source(bytes.fromhex(response.object_uuid))
    assert any(
        relation.relation_type == "considers_benefit_risk"
        and relation.target_uuid == benefit.object_uuid
        for relation in relations
    )


def test_multiple_current_residual_evaluations_are_rejected(repo):
    product, risk, policy, _, _ = _seed_context(repo)
    second, _ = repo.create_object(
        "residual_risk_evaluation",
        _residual_payload(risk, policy, acceptable=True),
        "other-evaluator",
        "other-evaluator",
    )
    repo.create_relation(
        source_uuid=second.object_uuid,
        source_version=second.current_version,
        target_uuid=risk.object_uuid,
        target_version=risk.current_version,
        relation_type="residual_of",
        created_by="other-evaluator",
    )
    repo.create_relation(
        source_uuid=second.object_uuid,
        source_version=second.current_version,
        target_uuid=policy.object_uuid,
        target_version=policy.current_version,
        relation_type="uses_risk_policy",
        created_by="other-evaluator",
    )
    repo.session.commit()

    with pytest.raises(InvalidRelationError):
        OverallResidualRiskService(repo).create_evaluation(
            product.uuid_hex,
            _request(product),
        )


def test_creator_cannot_approve_own_overall_residual_risk(repo):
    product, _, _, _, _ = _seed_context(repo)
    service = OverallResidualRiskService(repo)
    response = service.create_evaluation(
        product.uuid_hex,
        _request(product, evaluator="overall-reviewer"),
    )
    service.transition_state(response.object_uuid, "in_review", "overall-reviewer")

    with pytest.raises(SelfApprovalNotAllowedError):
        service.transition_state(response.object_uuid, "approved", "overall-reviewer")


def test_approval_rejects_product_risk_context_change_after_review(repo):
    product, _, policy, _, _ = _seed_context(repo)
    service = OverallResidualRiskService(repo)
    response = service.create_evaluation(
        product.uuid_hex,
        _request(product, evaluator="overall-reviewer"),
    )
    service.transition_state(response.object_uuid, "in_review", "overall-reviewer")

    _create_approved_risk_with_residual(
        repo,
        product,
        policy,
        suffix="LATE",
    )
    repo.session.commit()

    with pytest.raises(InvalidRelationError):
        service.transition_state(response.object_uuid, "approved", "overall-approver")

    stored = repo.get_by_uuid_hex(response.object_uuid)
    assert stored.lifecycle_state == "in_review"


def test_independent_approver_can_approve_overall_residual_risk(repo):
    product, _, _, _, _ = _seed_context(repo)
    service = OverallResidualRiskService(repo)
    response = service.create_evaluation(
        product.uuid_hex,
        _request(product, evaluator="overall-reviewer"),
    )
    service.transition_state(response.object_uuid, "in_review", "overall-reviewer")

    approved = service.transition_state(
        response.object_uuid,
        "approved",
        "overall-approver",
    )

    assert approved.lifecycle_state == "approved"

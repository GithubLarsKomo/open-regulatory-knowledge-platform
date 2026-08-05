"""Service tests for post-market safety information and Risk Impact Assessment."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import InvalidRelationError, SelfApprovalNotAllowedError
from orkp.domain.post_market_models import (
    PostMarketInformationCreateRequest,
    RiskImpactAssessmentCompleteRequest,
)
from orkp.domain.post_market_service import PostMarketRiskService


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _risk(repo):
    risk, _ = repo.create_object(
        "risk_analysis",
        {"risk_id": "R-PMS", "title": "Post-market risk"},
        "risk-owner",
        "risk-owner",
    )
    repo.session.commit()
    return risk


def _request(risk):
    return PostMarketInformationCreateRequest(
        risk_analysis={
            "object_uuid": risk.uuid_hex,
            "object_version": risk.current_version,
        },
        source_type="complaint",
        title="Unexpected false-negative complaint",
        description="A complaint reports an unexpected false-negative result.",
        observed_at="2026-08-05T10:00:00+00:00",
        reported_by_user_id="safety-reporter",
        external_reference="CMP-001",
    )


def _ingest(repo):
    risk = _risk(repo)
    result = PostMarketRiskService(repo).ingest_information(
        risk.uuid_hex,
        _request(risk),
    )
    return risk, result


def test_ingestion_creates_pending_assessment_and_exact_relations(repo):
    risk, result = _ingest(repo)

    assert result.information.lifecycle_state == "draft"
    assert result.impact_assessment.lifecycle_state == "draft"
    assert result.impact_assessment.payload.outcome == "pending"
    assert result.impact_assessment.payload.requires_risk_review is True
    assert result.impact_assessment.payload.assessor_user_id is None

    information_uuid = bytes.fromhex(result.information.object_uuid)
    assessment_uuid = bytes.fromhex(result.impact_assessment.object_uuid)

    information_relations = repo.list_active_relations_for_source(information_uuid)
    assert any(
        relation.relation_type == "impacts_risk"
        and relation.target_uuid == risk.object_uuid
        and relation.target_version == risk.current_version
        for relation in information_relations
    )

    risk_relations = repo.list_active_relations_for_source(risk.object_uuid)
    assert any(
        relation.relation_type == "informed_by"
        and relation.target_uuid == information_uuid
        and relation.target_version == 1
        for relation in risk_relations
    )

    assessment_relations = repo.list_active_relations_for_source(assessment_uuid)
    roles = {
        relation.properties.get("role")
        for relation in assessment_relations
        if relation.relation_type == "derived_from" and relation.properties
    }
    assert roles == {"impact_assessment_source", "assessed_risk"}


def test_new_ingestion_rejects_historical_risk_version(repo):
    risk = _risk(repo)
    request = _request(risk)
    repo.create_version(
        risk.object_uuid,
        {"risk_id": "R-PMS", "title": "Post-market risk v2"},
        "risk-owner",
    )
    repo.session.commit()

    with pytest.raises(InvalidRelationError):
        PostMarketRiskService(repo).ingest_information(risk.uuid_hex, request)


def test_no_change_completion_creates_new_version_and_clears_review_flag(repo):
    _, result = _ingest(repo)
    service = PostMarketRiskService(repo)

    completed = service.complete_assessment(
        result.impact_assessment.object_uuid,
        RiskImpactAssessmentCompleteRequest(
            outcome="no_change",
            rationale="The complaint is already covered by the established risk estimate.",
            assessor_user_id="risk-assessor",
        ),
    )

    assert completed.object_version == 2
    assert completed.payload.outcome == "no_change"
    assert completed.payload.requires_risk_review is False
    assert completed.payload.assessor_user_id == "risk-assessor"

    relations = repo.list_active_relations_for_source(
        bytes.fromhex(completed.object_uuid)
    )
    version_two_roles = {
        relation.properties.get("role")
        for relation in relations
        if relation.relation_type == "derived_from"
        and relation.source_version == 2
        and relation.properties
    }
    assert version_two_roles == {"impact_assessment_source", "assessed_risk"}


@pytest.mark.parametrize(
    "outcome",
    [
        "review_required",
        "risk_increase",
        "new_risk_identified",
        "control_effectiveness_concern",
    ],
)
def test_safety_relevant_outcomes_require_risk_review(repo, outcome):
    _, result = _ingest(repo)

    completed = PostMarketRiskService(repo).complete_assessment(
        result.impact_assessment.object_uuid,
        RiskImpactAssessmentCompleteRequest(
            outcome=outcome,
            rationale="The new information requires formal risk review.",
            assessor_user_id="risk-assessor",
        ),
    )

    assert completed.payload.requires_risk_review is True


def test_completion_is_blocked_if_post_market_information_changed(repo):
    _, result = _ingest(repo)
    information = repo.get_by_uuid_hex(result.information.object_uuid)
    payload = result.information.payload.model_dump()
    payload["description"] = "Updated source information."
    repo.create_version(information.object_uuid, payload, "safety-reporter")
    repo.session.commit()

    with pytest.raises(InvalidRelationError):
        PostMarketRiskService(repo).complete_assessment(
            result.impact_assessment.object_uuid,
            RiskImpactAssessmentCompleteRequest(
                outcome="review_required",
                rationale="Review is required.",
                assessor_user_id="risk-assessor",
            ),
        )


def test_pending_assessment_cannot_enter_review(repo):
    _, result = _ingest(repo)

    with pytest.raises(InvalidRelationError):
        PostMarketRiskService(repo).transition_assessment(
            result.impact_assessment.object_uuid,
            "in_review",
            "risk-assessor",
        )


def test_assessor_cannot_approve_own_assessment(repo):
    _, result = _ingest(repo)
    service = PostMarketRiskService(repo)
    completed = service.complete_assessment(
        result.impact_assessment.object_uuid,
        RiskImpactAssessmentCompleteRequest(
            outcome="review_required",
            rationale="Formal review is required.",
            assessor_user_id="risk-assessor",
        ),
    )
    service.transition_assessment(completed.object_uuid, "in_review", "risk-assessor")

    with pytest.raises(SelfApprovalNotAllowedError):
        service.transition_assessment(completed.object_uuid, "approved", "risk-assessor")


def test_independent_reviewer_can_approve_completed_assessment(repo):
    _, result = _ingest(repo)
    service = PostMarketRiskService(repo)
    completed = service.complete_assessment(
        result.impact_assessment.object_uuid,
        RiskImpactAssessmentCompleteRequest(
            outcome="no_change",
            rationale="No change to the current risk estimate is required.",
            assessor_user_id="risk-assessor",
        ),
    )
    service.transition_assessment(completed.object_uuid, "in_review", "risk-assessor")

    approved = service.transition_assessment(
        completed.object_uuid,
        "approved",
        "risk-approver",
    )

    assert approved.lifecycle_state == "approved"
    assert approved.object_version == 2


def test_approval_is_blocked_if_risk_version_changed_after_assessment(repo):
    risk, result = _ingest(repo)
    service = PostMarketRiskService(repo)
    completed = service.complete_assessment(
        result.impact_assessment.object_uuid,
        RiskImpactAssessmentCompleteRequest(
            outcome="review_required",
            rationale="Formal review is required.",
            assessor_user_id="risk-assessor",
        ),
    )
    service.transition_assessment(completed.object_uuid, "in_review", "risk-assessor")
    repo.create_version(
        risk.object_uuid,
        {"risk_id": "R-PMS", "title": "Post-market risk v2"},
        "risk-owner",
    )
    repo.session.commit()

    with pytest.raises(InvalidRelationError):
        service.transition_assessment(completed.object_uuid, "approved", "risk-approver")


def test_approval_requires_current_assessment_provenance(repo):
    _, result = _ingest(repo)
    service = PostMarketRiskService(repo)
    completed = service.complete_assessment(
        result.impact_assessment.object_uuid,
        RiskImpactAssessmentCompleteRequest(
            outcome="no_change",
            rationale="No change is required.",
            assessor_user_id="risk-assessor",
        ),
    )
    service.transition_assessment(completed.object_uuid, "in_review", "risk-assessor")

    assessment_uuid = bytes.fromhex(completed.object_uuid)
    relation = next(
        relation
        for relation in repo.list_active_relations_for_source(assessment_uuid)
        if relation.relation_type == "derived_from"
        and relation.source_version == completed.object_version
        and relation.properties
        and relation.properties.get("role") == "assessed_risk"
    )
    repo.session.delete(relation)
    repo.session.commit()

    with pytest.raises(InvalidRelationError):
        service.transition_assessment(completed.object_uuid, "approved", "risk-approver")

"""Lifecycle tests for control-verification supersession."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.control_verification_service import ControlVerificationService
from orkp.domain.exceptions import InvalidLifecycleStateError, InvalidRelationError
from orkp.domain.risk_models import ControlVerificationCreateRequest


def _setup_context(repo: RegulatoryObjectRepository):
    risk_analysis, _ = repo.create_object(
        "risk_analysis",
        {"analysis_id": "RA-1"},
        "u1",
        "u1",
    )
    risk_control, _ = repo.create_object(
        "risk_control",
        {"control_id": "RC-1", "description": "Test control"},
        "u1",
        "u1",
    )
    risk_policy, _ = repo.create_object(
        "risk_policy",
        {"policy_id": "RP-1"},
        "u1",
        "u1",
    )
    evidence, _ = repo.create_object(
        "evidence",
        {"evidence_id": "EV-1", "summary": "Verification evidence"},
        "u1",
        "u1",
    )
    initial_evaluation, _ = repo.create_object(
        "initial_risk_evaluation",
        {
            "evaluation_id": "IRE-1",
            "risk_analysis_uuid": risk_analysis.uuid_hex,
            "risk_analysis_version": 1,
            "severity": "moderate",
            "probability": "possible",
            "calculated_risk_level": "high",
            "acceptable": False,
            "action_required": "control_required",
            "risk_policy_uuid": risk_policy.uuid_hex,
            "risk_policy_version": 1,
            "policy_revision": "1.0",
            "evaluator_user_id": "u1",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        },
        "u1",
        "u1",
    )
    repo.create_relation(
        source_uuid=risk_analysis.object_uuid,
        source_version=1,
        target_uuid=risk_control.object_uuid,
        target_version=1,
        relation_type="controlled_by",
        created_by="u1",
    )
    for obj in (risk_policy, evidence):
        repo.transition_state(obj.object_uuid, "in_review", "u1")
        repo.transition_state(obj.object_uuid, "approved", "u2")
    repo.session.commit()
    return {
        "risk_analysis": risk_analysis,
        "risk_control": risk_control,
        "risk_policy": risk_policy,
        "evidence": evidence,
        "initial_evaluation": initial_evaluation,
    }


def _request(context, owner: str, supersedes=None):
    return ControlVerificationCreateRequest(
        risk_analysis={
            "object_uuid": context["risk_analysis"].uuid_hex,
            "object_version": 1,
        },
        risk_control={
            "object_uuid": context["risk_control"].uuid_hex,
            "object_version": 1,
        },
        initial_evaluation={
            "object_uuid": context["initial_evaluation"].uuid_hex,
            "object_version": 1,
        },
        risk_policy={
            "object_uuid": context["risk_policy"].uuid_hex,
            "object_version": 1,
        },
        evidence=[{"object_uuid": context["evidence"].uuid_hex, "object_version": 1}],
        supersedes=supersedes,
        verification_method="test",
        verification_scope="Implementation and effectiveness",
        implementation_verified=True,
        effectiveness_verified=True,
        no_new_uncontrolled_risks=True,
        effectiveness_result="effective",
        conclusion="passed",
        verified_by_user_id=owner,
    )


def _make_effective(service, verification, owner: str):
    service.transition_state(verification.object_uuid, "in_review", owner)
    service.transition_state(verification.object_uuid, "approved", "approver")
    return service.transition_state(verification.object_uuid, "effective", owner)


def test_supersession_obsoletes_prior_only_when_successor_becomes_effective():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RegulatoryObjectRepository(session)
        context = _setup_context(repo)
        service = ControlVerificationService(repo)

        prior = service.create_verification(
            context["risk_control"].uuid_hex,
            _request(context, "owner-1"),
        )
        prior = _make_effective(service, prior, "owner-1")
        assert prior.eligible_for_residual_evaluation is True

        successor = service.create_verification(
            context["risk_control"].uuid_hex,
            _request(
                context,
                "owner-2",
                supersedes={
                    "object_uuid": prior.object_uuid,
                    "object_version": prior.object_version,
                },
            ),
        )

        prior_object = repo.get_by_uuid_hex(prior.object_uuid)
        assert prior_object.lifecycle_state == "effective"
        supersedes = [
            relation
            for relation in repo.list_active_relations_for_source(
                bytes.fromhex(successor.object_uuid)
            )
            if relation.relation_type == "supersedes"
        ]
        assert len(supersedes) == 1
        assert supersedes[0].target_uuid == bytes.fromhex(prior.object_uuid)
        assert supersedes[0].target_version == prior.object_version

        successor = _make_effective(service, successor, "owner-2")

        prior_object = repo.get_by_uuid_hex(prior.object_uuid)
        assert prior_object.lifecycle_state == "obsolete"
        prior_response = service.get_verification(
            prior.object_uuid, prior.object_version
        )
        assert prior_response.eligible_for_residual_evaluation is False
        assert successor.eligible_for_residual_evaluation is True


def test_supersession_rejects_parallel_successor():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RegulatoryObjectRepository(session)
        context = _setup_context(repo)
        service = ControlVerificationService(repo)

        prior = service.create_verification(
            context["risk_control"].uuid_hex,
            _request(context, "owner-1"),
        )
        prior = _make_effective(service, prior, "owner-1")
        supersedes = {
            "object_uuid": prior.object_uuid,
            "object_version": prior.object_version,
        }
        service.create_verification(
            context["risk_control"].uuid_hex,
            _request(context, "owner-2", supersedes=supersedes),
        )

        with pytest.raises(InvalidRelationError):
            service.create_verification(
                context["risk_control"].uuid_hex,
                _request(context, "owner-3", supersedes=supersedes),
            )


def test_supersession_requires_effective_prior():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RegulatoryObjectRepository(session)
        context = _setup_context(repo)
        service = ControlVerificationService(repo)

        prior = service.create_verification(
            context["risk_control"].uuid_hex,
            _request(context, "owner-1"),
        )

        with pytest.raises(InvalidLifecycleStateError):
            service.create_verification(
                context["risk_control"].uuid_hex,
                _request(
                    context,
                    "owner-2",
                    supersedes={
                        "object_uuid": prior.object_uuid,
                        "object_version": prior.object_version,
                    },
                ),
            )

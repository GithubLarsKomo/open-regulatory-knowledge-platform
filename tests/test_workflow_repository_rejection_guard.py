"""Repository-level regressions for mandatory rejection rationale."""

from uuid import UUID

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from orkp.db.models import ApprovalRecord, Base, EventLog
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import InvalidLifecycleTransitionError


@pytest.fixture()
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _in_review(repo: RegulatoryObjectRepository):
    obj, _ = repo.create_object(
        "internal_document",
        {"title": "Repository rejection guard"},
        "author",
        "author",
    )
    repo.transition_state(obj.object_uuid, "in_review", "author")
    repo.session.flush()
    return obj


def _event_count(repo: RegulatoryObjectRepository, object_uuid: bytes) -> int:
    return repo.session.execute(
        select(func.count()).select_from(EventLog).where(
            EventLog.aggregate_uuid == object_uuid
        )
    ).scalar_one()


def _approval_count(repo: RegulatoryObjectRepository, object_uuid: bytes) -> int:
    return repo.session.execute(
        select(func.count()).select_from(ApprovalRecord).where(
            ApprovalRecord.object_uuid == object_uuid
        )
    ).scalar_one()


@pytest.mark.parametrize("comments", [None, "", "   \t"])
def test_direct_repository_rejection_requires_non_blank_comments(repo, comments):
    obj = _in_review(repo)
    lock_before = obj.lock_version
    events_before = _event_count(repo, obj.object_uuid)
    approvals_before = _approval_count(repo, obj.object_uuid)

    with pytest.raises(
        InvalidLifecycleTransitionError,
        match="non-blank reviewer comments",
    ):
        repo.transition_state(
            obj.object_uuid,
            "rejected",
            "reviewer",
            comments=comments,
        )

    repo.session.flush()
    assert obj.lifecycle_state == "in_review"
    assert obj.lock_version == lock_before
    assert _event_count(repo, obj.object_uuid) == events_before
    assert _approval_count(repo, obj.object_uuid) == approvals_before


def test_direct_repository_rejection_persists_exact_approval_metadata(repo):
    obj = _in_review(repo)

    repo.transition_state(
        obj.object_uuid,
        "rejected",
        "reviewer-17",
        comments="Insufficient supporting evidence.",
    )
    repo.session.flush()

    record = repo.session.execute(
        select(ApprovalRecord).where(ApprovalRecord.object_uuid == obj.object_uuid)
    ).scalar_one()

    assert obj.lifecycle_state == "rejected"
    assert record.object_uuid == UUID(obj.uuid_hex).bytes
    assert record.version_no == 1
    assert record.decision == "rejected"
    assert record.approver_user_id == "reviewer-17"
    assert record.comments == "Insufficient supporting evidence."
    assert record.decision_timestamp is not None

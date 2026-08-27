"""Regression tests for workflow rejection rationale persistence."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orkp.api.main import create_app
from orkp.db.models import ApprovalRecord, Base


@pytest.fixture()
def workflow_context():
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


def _create_in_review_object(client: TestClient) -> str:
    created = client.post(
        "/api/v1/objects",
        json={
            "object_type": "internal_document",
            "payload": {"title": "Workflow test"},
            "owner_user_id": "author",
        },
    )
    assert created.status_code == 201
    object_uuid = created.json()["object_uuid"]

    submitted = client.post(
        f"/api/v1/objects/{object_uuid}/transitions",
        json={"new_state": "in_review", "actor_user_id": "author"},
    )
    assert submitted.status_code == 200
    return object_uuid


@pytest.mark.parametrize("comments", [None, "", "   \t"])
def test_rejection_requires_non_blank_reviewer_comments(workflow_context, comments):
    client, _ = workflow_context
    object_uuid = _create_in_review_object(client)
    payload = {
        "new_state": "rejected",
        "actor_user_id": "reviewer",
        "comments": comments,
    }

    response = client.post(
        f"/api/v1/objects/{object_uuid}/transitions",
        json=payload,
    )

    assert response.status_code == 422
    loaded = client.get(f"/api/v1/objects/{object_uuid}")
    assert loaded.status_code == 200
    assert loaded.json()["lifecycle_state"] == "in_review"


def test_rejection_persists_exact_decision_metadata(workflow_context):
    client, session_factory = workflow_context
    object_uuid = _create_in_review_object(client)

    rejected = client.post(
        f"/api/v1/objects/{object_uuid}/transitions",
        json={
            "new_state": "rejected",
            "actor_user_id": "reviewer-17",
            "comments": "Insufficient supporting evidence.",
        },
    )

    assert rejected.status_code == 200
    assert rejected.json()["lifecycle_state"] == "rejected"

    with session_factory() as session:
        records = list(
            session.execute(
                select(ApprovalRecord).where(
                    ApprovalRecord.object_uuid == UUID(object_uuid).bytes
                )
            )
            .scalars()
            .all()
        )

    assert len(records) == 1
    record = records[0]
    assert record.version_no == 1
    assert record.decision == "rejected"
    assert record.approver_user_id == "reviewer-17"
    assert record.comments == "Insufficient supporting evidence."
    assert record.decision_timestamp is not None

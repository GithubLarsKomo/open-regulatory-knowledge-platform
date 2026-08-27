"""API regressions for persisted workflow approval/rejection history."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orkp.api.main import create_app
from orkp.db.models import Base


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return TestClient(create_app(session_factory_override=session_factory))


def _create_object(client: TestClient) -> str:
    created = client.post(
        "/api/v1/objects",
        json={
            "object_type": "internal_document",
            "payload": {"title": "Approval history"},
            "owner_user_id": "author",
        },
    )
    assert created.status_code == 201
    return created.json()["object_uuid"]


def _transition(
    client: TestClient,
    object_uuid: str,
    new_state: str,
    actor: str,
    comments: str | None = None,
):
    payload = {"new_state": new_state, "actor_user_id": actor}
    if comments is not None:
        payload["comments"] = comments
    response = client.post(
        f"/api/v1/objects/{object_uuid}/transitions",
        json=payload,
    )
    assert response.status_code == 200
    return response


def test_draft_object_has_empty_approval_history(client):
    object_uuid = _create_object(client)

    response = client.get(f"/api/v1/objects/{object_uuid}/approvals")

    assert response.status_code == 200
    assert response.json() == []


def test_rejection_history_exposes_exact_decision_metadata(client):
    object_uuid = _create_object(client)
    _transition(client, object_uuid, "in_review", "author")
    _transition(
        client,
        object_uuid,
        "rejected",
        "reviewer-17",
        "Insufficient supporting evidence.",
    )

    response = client.get(f"/api/v1/objects/{object_uuid}/approvals")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["object_uuid"] == object_uuid
    assert body[0]["version_no"] == 1
    assert body[0]["decision"] == "rejected"
    assert body[0]["approver_user_id"] == "reviewer-17"
    assert body[0]["comments"] == "Insufficient supporting evidence."
    assert body[0]["signature_data"] is None
    assert body[0]["decision_timestamp"]
    assert len(body[0]["approval_uuid"]) == 32


def test_history_is_deterministic_across_reject_revision_and_approval(client):
    object_uuid = _create_object(client)
    _transition(client, object_uuid, "in_review", "author")
    _transition(client, object_uuid, "rejected", "reviewer-a", "Revise evidence.")
    _transition(client, object_uuid, "draft", "author")
    _transition(client, object_uuid, "in_review", "author")
    _transition(client, object_uuid, "approved", "reviewer-b", "Approved.")

    first = client.get(f"/api/v1/objects/{object_uuid}/approvals")
    second = client.get(f"/api/v1/objects/{object_uuid}/approvals")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert {item["decision"] for item in first.json()} == {"rejected", "approved"}
    assert {item["approver_user_id"] for item in first.json()} == {
        "reviewer-a",
        "reviewer-b",
    }


def test_approval_history_returns_404_for_missing_object(client):
    response = client.get("/api/v1/objects/00000000000000000000000000000000/approvals")

    assert response.status_code == 404

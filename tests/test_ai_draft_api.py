"""REST regressions for governed auditable AI draft records."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orkp.api.main import create_app
from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository


@pytest.fixture
def api_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    client = TestClient(create_app(session_factory_override=session_factory))
    return client, session_factory


def _source(session_factory):
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        source, _ = repo.create_object(
            "evidence",
            {"evidence_type": "literature", "title": "AI grounding source"},
            "source-owner",
            "source-owner",
        )
        session.commit()
        return source.uuid_hex


def _body(source_uuid, **overrides):
    body = {
        "prompt_text": "Draft a grounded statement.",
        "model_id": "provider/model-1",
        "context_refs": [
            {"object_uuid": source_uuid, "object_version": 1},
        ],
        "blocks": [
            {
                "block_id": "fact",
                "statement_kind": "retrieved_fact",
                "text": "The cited source contains the relevant result.",
                "source_refs": [
                    {"object_uuid": source_uuid, "object_version": 1},
                ],
            }
        ],
        "confidence_score": 0.75,
        "initiated_by_user_id": "author",
        "target_domain": "general",
    }
    body.update(overrides)
    return body


def test_ai_draft_api_create_get_and_regenerate_preserve_audit_versions(api_context):
    client, session_factory = api_context
    source_uuid = _source(session_factory)

    created = client.post("/api/v1/ai/drafts", json=_body(source_uuid))

    assert created.status_code == 201, created.text
    body = created.json()
    draft_uuid = body["draft_uuid"]
    assert body["object_version"] == 1
    assert body["lifecycle_state"] == "draft"
    assert body["payload"]["regulatory_status"] == "unapproved_draft"
    assert body["payload"]["approval_authority"] == "human_workflow"

    fetched = client.get(f"/api/v1/ai/drafts/{draft_uuid}")
    assert fetched.status_code == 200
    assert fetched.json() == body

    regenerated_body = _body(
        source_uuid,
        prompt_text="Regenerate with narrower wording.",
        model_id="provider/model-2",
    )
    regenerated_body["actor_user_id"] = "editor"
    regenerated = client.post(
        f"/api/v1/ai/drafts/{draft_uuid}/regenerate",
        json=regenerated_body,
    )

    assert regenerated.status_code == 201, regenerated.text
    assert regenerated.json()["draft_uuid"] == draft_uuid
    assert regenerated.json()["object_version"] == 2
    versions = client.get(f"/api/v1/objects/{draft_uuid}/versions")
    assert versions.status_code == 200
    assert [item["version_no"] for item in versions.json()] == [2, 1]
    assert versions.json()[1]["payload"]["prompt_text"] == "Draft a grounded statement."
    assert versions.json()[0]["payload"]["prompt_text"] == (
        "Regenerate with narrower wording."
    )


def test_ai_draft_api_rejects_missing_grounding_version(api_context):
    client, session_factory = api_context
    source_uuid = _source(session_factory)
    body = _body(source_uuid)
    body["context_refs"] = [{"object_uuid": source_uuid, "object_version": 99}]
    body["blocks"][0]["source_refs"] = [
        {"object_uuid": source_uuid, "object_version": 99}
    ]

    response = client.post("/api/v1/ai/drafts", json=body)

    assert response.status_code == 404
    assert "v99 not found" in response.json()["detail"]


def test_generic_core_api_cannot_create_ai_draft(api_context):
    client, _ = api_context

    response = client.post(
        "/api/v1/objects",
        json={
            "object_type": "ai_draft",
            "payload": {"regulatory_status": "approved"},
            "owner_user_id": "attacker",
        },
    )

    assert response.status_code == 409
    assert "domain-specific creation workflow" in response.json()["detail"]


def test_generic_core_api_cannot_version_or_approve_ai_draft(api_context):
    client, session_factory = api_context
    source_uuid = _source(session_factory)
    created = client.post("/api/v1/ai/drafts", json=_body(source_uuid))
    draft_uuid = created.json()["draft_uuid"]

    version = client.post(
        f"/api/v1/objects/{draft_uuid}/versions",
        json={"payload": {"regulatory_status": "approved"}, "created_by": "attacker"},
    )
    transition = client.post(
        f"/api/v1/objects/{draft_uuid}/transitions",
        json={"new_state": "in_review", "actor_user_id": "attacker"},
    )

    assert version.status_code == 409
    assert "domain-specific versioning workflow" in version.json()["detail"]
    assert transition.status_code == 409
    assert "domain-specific workflow" in transition.json()["detail"]


def test_ai_draft_api_rejects_risk_decision_fields(api_context):
    client, session_factory = api_context
    source_uuid = _source(session_factory)
    body = _body(
        source_uuid,
        target_domain="risk",
        risk_support={"rationale": "Draft rationale", "acceptable": True},
    )

    response = client.post("/api/v1/ai/drafts", json=body)

    assert response.status_code == 403
    assert "acceptable" in response.json()["detail"]

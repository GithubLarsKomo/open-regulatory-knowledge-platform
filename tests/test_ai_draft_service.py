"""Domain regressions for auditable grounded AI draft records."""

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.ai_draft_models import AIDraftCreateRequest, AIDraftRegenerateRequest
from orkp.domain.ai_draft_service import AIDraftService
from orkp.domain.exceptions import (
    AuthorizationError,
    InvalidPersistedPayloadError,
    ObjectNotFoundError,
    ObjectTypeMismatchError,
)


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _source(repo, object_type="evidence", payload=None):
    source, _ = repo.create_object(
        object_type,
        payload or {"title": "Grounding source"},
        "source-owner",
        "source-owner",
    )
    repo.session.commit()
    return source


def _request(source, **overrides):
    payload = {
        "prompt_text": "Draft a grounded regulatory statement.",
        "model_id": "provider/model-1",
        "context_refs": [
            {"object_uuid": source.uuid_hex, "object_version": 1},
        ],
        "blocks": [
            {
                "block_id": "fact-1",
                "statement_kind": "retrieved_fact",
                "text": "The source reports the measured result.",
                "source_refs": [
                    {"object_uuid": source.uuid_hex, "object_version": 1},
                ],
            },
            {
                "block_id": "wording-1",
                "statement_kind": "generated_wording",
                "text": "Draft wording based on the cited source.",
                "source_refs": [
                    {"object_uuid": source.uuid_hex, "object_version": 1},
                ],
            },
        ],
        "confidence_score": 0.82,
        "initiated_by_user_id": "author",
    }
    payload.update(overrides)
    return AIDraftCreateRequest(**payload)


def test_create_ai_draft_persists_prompt_grounding_provenance_and_draft_status(repo):
    source = _source(repo)
    source_events_before = len(repo.get_event_history(source.object_uuid))

    response = AIDraftService(repo).create_draft(_request(source))

    assert response.object_version == 1
    assert response.lifecycle_state == "draft"
    assert response.payload.schema_version == "ai-draft-1.0"
    assert response.payload.regulatory_status == "unapproved_draft"
    assert response.payload.approval_authority == "human_workflow"
    assert response.payload.ai_may_approve is False
    assert response.payload.prompt_text == "Draft a grounded regulatory statement."
    assert response.payload.model_id == "provider/model-1"
    assert response.payload.confidence_score == 0.82
    assert [block.statement_kind for block in response.payload.blocks] == [
        "retrieved_fact",
        "generated_wording",
    ]
    assert response.payload.context_refs[0].object_uuid == source.uuid_hex
    assert len(repo.get_event_history(source.object_uuid)) == source_events_before


def test_ai_draft_rejects_missing_exact_context_version(repo):
    source = _source(repo)
    request = _request(
        source,
        context_refs=[{"object_uuid": source.uuid_hex, "object_version": 99}],
        blocks=[
            {
                "block_id": "fact",
                "statement_kind": "retrieved_fact",
                "text": "Fact",
                "source_refs": [
                    {"object_uuid": source.uuid_hex, "object_version": 99}
                ],
            }
        ],
    )

    with pytest.raises(ObjectNotFoundError, match="v99 not found"):
        AIDraftService(repo).create_draft(request)


def test_ai_draft_model_rejects_citation_outside_frozen_context(repo):
    source = _source(repo)
    other = _source(repo, payload={"title": "Other source"})

    with pytest.raises(ValidationError, match="outside context_refs"):
        _request(
            source,
            blocks=[
                {
                    "block_id": "fact",
                    "statement_kind": "retrieved_fact",
                    "text": "Fact",
                    "source_refs": [
                        {"object_uuid": other.uuid_hex, "object_version": 1}
                    ],
                }
            ],
        )


def test_ai_draft_model_rejects_ungrounded_generated_wording(repo):
    source = _source(repo)

    with pytest.raises(ValidationError):
        _request(
            source,
            blocks=[
                {
                    "block_id": "wording",
                    "statement_kind": "generated_wording",
                    "text": "Ungrounded wording",
                    "source_refs": [],
                }
            ],
        )


def test_regeneration_creates_new_version_and_preserves_historical_payload(repo):
    source = _source(repo)
    service = AIDraftService(repo)
    created = service.create_draft(_request(source))
    request = AIDraftRegenerateRequest(
        **_request(
            source,
            prompt_text="Regenerate with a narrower wording.",
            model_id="provider/model-2",
        ).model_dump(mode="json"),
        actor_user_id="editor",
    )

    regenerated = service.regenerate_draft(created.draft_uuid, request)

    assert regenerated.draft_uuid == created.draft_uuid
    assert regenerated.object_version == 2
    assert regenerated.payload.prompt_text == "Regenerate with a narrower wording."
    assert regenerated.payload.model_id == "provider/model-2"
    obj = repo.get_by_uuid_hex(created.draft_uuid)
    versions = repo.list_versions(obj.object_uuid)
    assert [version.version_no for version in versions] == [1, 2]
    assert versions[0].payload_json["prompt_text"] == "Draft a grounded regulatory statement."
    assert versions[1].payload_json["prompt_text"] == "Regenerate with a narrower wording."


def test_risk_targeted_ai_draft_rejects_decision_fields(repo):
    source = _source(repo, object_type="risk_analysis", payload={"risk_id": "RA-AI"})
    request = _request(
        source,
        target_domain="risk",
        risk_support={"rationale": "Draft rationale", "acceptable": True},
    )

    with pytest.raises(AuthorizationError, match="acceptable"):
        AIDraftService(repo).create_draft(request)


def test_ai_draft_cannot_be_used_as_grounding_source_for_another_ai_draft(repo):
    source = _source(repo)
    first = AIDraftService(repo).create_draft(_request(source))
    ai_source = repo.get_by_uuid_hex(first.draft_uuid)

    with pytest.raises(ObjectTypeMismatchError, match="cannot be used as grounding"):
        AIDraftService(repo).create_draft(_request(ai_source))


def test_get_draft_rejects_tampered_persisted_payload(repo):
    draft, _ = repo.create_object(
        "ai_draft",
        {
            "schema_version": "ai-draft-1.0",
            "regulatory_status": "approved",
            "approval_authority": "human_workflow",
            "ai_may_approve": False,
            "prompt_text": "Tampered",
            "model_id": "model",
            "context_refs": [],
            "blocks": [],
            "confidence_score": 1.0,
            "initiated_by_user_id": "attacker",
            "target_domain": "general",
            "risk_support": None,
        },
        "attacker",
        "attacker",
    )
    repo.session.commit()

    with pytest.raises(InvalidPersistedPayloadError):
        AIDraftService(repo).get_draft(draft.uuid_hex)

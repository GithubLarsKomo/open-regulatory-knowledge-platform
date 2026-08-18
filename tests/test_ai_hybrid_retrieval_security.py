"""Security regression for hybrid retrieval grounding boundaries."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.ai_retrieval_models import HybridRetrievalRequest
from orkp.domain.ai_retrieval_service import HybridRetrievalService
from orkp.domain.exceptions import ObjectTypeMismatchError


class EmptyVectorAdapter:
    def search(self, query_text: str, limit: int):
        return []


def test_ai_draft_cannot_be_used_as_graph_retrieval_seed():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RegulatoryObjectRepository(session)
        draft, _ = repo.create_object(
            "ai_draft",
            {"prompt_text": "generated context"},
            "author",
            "author",
        )
        session.commit()

        with pytest.raises(ObjectTypeMismatchError, match="cannot be used as a graph retrieval seed"):
            HybridRetrievalService(repo, EmptyVectorAdapter()).retrieve(
                HybridRetrievalRequest(
                    query_text="context",
                    graph_seed_refs=[
                        {"object_uuid": draft.uuid_hex, "object_version": 1}
                    ],
                )
            )

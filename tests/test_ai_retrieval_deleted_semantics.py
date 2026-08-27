"""Semantic regressions for deleted objects in hybrid AI retrieval."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.ai_retrieval_models import HybridRetrievalRequest, RetrievalHit
from orkp.domain.ai_retrieval_service import HybridRetrievalService
from orkp.domain.exceptions import ObjectNotFoundError
from orkp.domain.risk_models import VersionedObjectReference


class StaticVectorAdapter:
    def __init__(self, hits):
        self.hits = list(hits)

    def search(self, query_text: str, limit: int):
        return list(self.hits[:limit])


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _create(repo, object_type: str, payload: dict):
    obj, _ = repo.create_object(object_type, payload, "owner", "owner")
    repo.session.commit()
    return obj


def test_deleted_vector_hit_is_rejected_as_not_found(repo):
    evidence = _create(repo, "evidence", {"title": "Deleted grounding source"})
    repo.soft_delete(evidence.object_uuid, "owner")
    repo.session.commit()

    vector = StaticVectorAdapter(
        [
            RetrievalHit(
                reference=VersionedObjectReference(
                    object_uuid=evidence.uuid_hex,
                    object_version=1,
                ),
                object_type="evidence",
                channel="vector",
                score=1.0,
            )
        ]
    )

    with pytest.raises(ObjectNotFoundError, match="Retrieval hit object"):
        HybridRetrievalService(repo, vector).retrieve(
            HybridRetrievalRequest(query_text="deleted grounding source")
        )


def test_deleted_graph_neighbor_is_rejected_as_not_found(repo):
    claim = _create(repo, "claim", {"wording": "Grounded claim"})
    evidence = _create(repo, "evidence", {"title": "Deleted graph evidence"})
    repo.create_relation(
        source_uuid=evidence.object_uuid,
        source_version=1,
        target_uuid=claim.object_uuid,
        target_version=1,
        relation_type="supported_by",
        created_by="owner",
    )
    repo.session.commit()
    repo.soft_delete(evidence.object_uuid, "owner")
    repo.session.commit()

    with pytest.raises(ObjectNotFoundError, match="Retrieval hit object"):
        HybridRetrievalService(repo, StaticVectorAdapter([])).retrieve(
            HybridRetrievalRequest(
                query_text="unmatched",
                graph_seed_refs=[
                    {
                        "object_uuid": claim.uuid_hex,
                        "object_version": 1,
                    }
                ],
                graph_depth=1,
            )
        )

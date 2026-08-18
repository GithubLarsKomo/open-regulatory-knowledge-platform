"""Regressions for deterministic keyword/vector/graph hybrid retrieval."""

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.ai_retrieval_models import (
    HybridRetrievalRequest,
    RetrievalHit,
)
from orkp.domain.ai_retrieval_service import (
    GraphRetrievalAdapter,
    HybridRetrievalService,
    ObjectStoreKeywordRetrievalAdapter,
)
from orkp.domain.exceptions import (
    ObjectTypeMismatchError,
    ObjectVersionNotFoundError,
)


class RecordingVectorAdapter:
    def __init__(self, hits=None):
        self.hits = hits or []
        self.calls = []

    def search(self, query_text: str, limit: int):
        self.calls.append((query_text, limit))
        return list(self.hits[:limit])


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _object(repo, object_type, payload, owner="owner"):
    obj, _ = repo.create_object(object_type, payload, owner, owner)
    repo.session.commit()
    return obj


def _context(repo):
    product = _object(
        repo,
        "product",
        {"product_id": "P-HYBRID", "name": "Hybrid Assay"},
    )
    claim = _object(
        repo,
        "claim",
        {
            "claim_id": "CL-HYBRID",
            "wording": "Clinical sensitivity exceeds ninety percent",
        },
    )
    evidence = _object(
        repo,
        "evidence",
        {
            "evidence_id": "EV-HYBRID",
            "title": "Clinical sensitivity validation dataset",
        },
    )
    repo.create_relation(
        source_uuid=product.object_uuid,
        source_version=1,
        target_uuid=claim.object_uuid,
        target_version=1,
        relation_type="has_claim",
        created_by="owner",
    )
    repo.create_relation(
        source_uuid=evidence.object_uuid,
        source_version=1,
        target_uuid=claim.object_uuid,
        target_version=1,
        relation_type="supported_by",
        created_by="owner",
    )
    repo.session.commit()
    return product, claim, evidence


def _hit(obj, channel="vector", score=0.9, version=1, object_type=None):
    return RetrievalHit(
        reference={"object_uuid": obj.uuid_hex, "object_version": version},
        object_type=object_type or obj.object_type,
        channel=channel,
        score=score,
    )


def test_keyword_retrieval_returns_current_exact_version_deterministically(repo):
    evidence = _object(
        repo,
        "evidence",
        {"title": "Clinical sensitivity dataset"},
    )
    repo.create_version(
        evidence.object_uuid,
        {"title": "Clinical sensitivity validation dataset"},
        "editor",
    )
    repo.session.commit()

    adapter = ObjectStoreKeywordRetrievalAdapter(repo)
    first = adapter.search("clinical sensitivity", limit=10)
    second = adapter.search("clinical sensitivity", limit=10)

    assert first == second
    assert len(first) == 1
    assert first[0].reference.object_uuid == evidence.uuid_hex
    assert first[0].reference.object_version == 2
    assert first[0].channel == "keyword"
    assert 0 < first[0].score <= 1


def test_graph_retrieval_uses_exact_seed_version_and_distance_score(repo):
    product, claim, evidence = _context(repo)

    hits = GraphRetrievalAdapter(repo).search(
        [{"object_uuid": claim.uuid_hex, "object_version": 1}],
        depth=1,
        limit=10,
    )

    assert {(hit.reference.object_uuid, hit.score) for hit in hits} == {
        (product.uuid_hex, 1.0),
        (evidence.uuid_hex, 1.0),
    }
    assert all(hit.channel == "graph" for hit in hits)


def test_hybrid_fusion_merges_same_exact_ref_across_all_three_channels(repo):
    _, claim, evidence = _context(repo)
    vector = RecordingVectorAdapter([_hit(evidence, score=0.8)])
    request = HybridRetrievalRequest(
        query_text="clinical sensitivity",
        graph_seed_refs=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
        max_results=10,
    )

    response = HybridRetrievalService(repo, vector).retrieve(request)
    evidence_result = next(
        result for result in response.results if result.reference.object_uuid == evidence.uuid_hex
    )

    assert evidence_result.reference.object_version == 1
    assert evidence_result.channels == ["keyword", "vector", "graph"]
    assert evidence_result.keyword_score > 0
    assert evidence_result.vector_score == 0.8
    assert evidence_result.graph_score == 1.0
    assert evidence_result.fused_score > evidence_result.vector_score * 0.45
    assert vector.calls == [("clinical sensitivity", 20)]


def test_hybrid_results_are_deterministic_with_stable_tie_breaking(repo):
    first = _object(repo, "evidence", {"title": "alpha source"})
    second = _object(repo, "evidence", {"title": "beta source"})
    vector = RecordingVectorAdapter([
        _hit(second, score=0.5),
        _hit(first, score=0.5),
    ])
    request = HybridRetrievalRequest(query_text="unmatched", max_results=10)
    service = HybridRetrievalService(repo, vector)

    one = service.retrieve(request)
    two = service.retrieve(request)

    assert one.model_dump(mode="json") == two.model_dump(mode="json")
    expected = sorted([first.uuid_hex, second.uuid_hex])
    assert [result.reference.object_uuid for result in one.results] == expected


def test_vector_adapter_unknown_exact_version_is_rejected(repo):
    evidence = _object(repo, "evidence", {"title": "source"})
    vector = RecordingVectorAdapter([_hit(evidence, version=99)])

    with pytest.raises(ObjectVersionNotFoundError, match="v99 not found"):
        HybridRetrievalService(repo, vector).retrieve(
            HybridRetrievalRequest(query_text="anything")
        )


def test_vector_adapter_wrong_object_type_is_rejected(repo):
    evidence = _object(repo, "evidence", {"title": "source"})
    vector = RecordingVectorAdapter([
        _hit(evidence, object_type="claim"),
    ])

    with pytest.raises(ObjectTypeMismatchError, match="does not match Object Store type"):
        HybridRetrievalService(repo, vector).retrieve(
            HybridRetrievalRequest(query_text="anything")
        )


def test_vector_adapter_wrong_channel_is_rejected(repo):
    evidence = _object(repo, "evidence", {"title": "source"})
    vector = RecordingVectorAdapter([_hit(evidence, channel="keyword")])

    with pytest.raises(ObjectTypeMismatchError, match="vector retrieval adapter returned keyword"):
        HybridRetrievalService(repo, vector).retrieve(
            HybridRetrievalRequest(query_text="anything")
        )


def test_ai_draft_hits_are_excluded_from_keyword_and_vector_results(repo):
    draft = _object(
        repo,
        "ai_draft",
        {"prompt_text": "clinical sensitivity", "text": "generated"},
    )
    vector = RecordingVectorAdapter([_hit(draft)])

    response = HybridRetrievalService(repo, vector).retrieve(
        HybridRetrievalRequest(query_text="clinical sensitivity")
    )

    assert response.results == []


def test_retrieval_is_read_only_for_source_objects(repo):
    _, claim, evidence = _context(repo)
    before_claim = len(repo.get_event_history(claim.object_uuid))
    before_evidence = len(repo.get_event_history(evidence.object_uuid))
    vector = RecordingVectorAdapter([_hit(evidence)])

    HybridRetrievalService(repo, vector).retrieve(
        HybridRetrievalRequest(
            query_text="clinical sensitivity",
            graph_seed_refs=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
        )
    )

    assert len(repo.get_event_history(claim.object_uuid)) == before_claim
    assert len(repo.get_event_history(evidence.object_uuid)) == before_evidence


def test_request_rejects_duplicate_exact_graph_seeds(repo):
    claim = _object(repo, "claim", {"wording": "Claim"})
    seed = {"object_uuid": claim.uuid_hex, "object_version": 1}

    with pytest.raises(ValidationError, match="graph_seed_refs must not contain duplicate"):
        HybridRetrievalRequest(
            query_text="claim",
            graph_seed_refs=[seed, seed],
        )

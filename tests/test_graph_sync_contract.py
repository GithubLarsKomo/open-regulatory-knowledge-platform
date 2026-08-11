"""Regressions for deterministic graph synchronization adapter contract."""

from copy import deepcopy
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import GraphSynchronizationError
from orkp.domain.graph_sync_models import GraphSyncBatch, GraphSyncResult
from orkp.domain.graph_sync_service import GraphSyncService


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _context(repo):
    product, _ = repo.create_object(
        "product",
        {"product_id": "P-SYNC", "name": "Sync Product"},
        "owner",
        "owner",
    )
    claim, _ = repo.create_object(
        "claim",
        {
            "claim_type": "clinical",
            "claim_category": "clinical",
            "confidence": "high",
            "severity": "medium",
            "jurisdiction": "EU",
            "language": "en",
            "wording": "Sync claim v1",
            "regulatory_scope": [],
        },
        "claim-owner",
        "claim-owner",
    )
    relation = repo.create_relation(
        product.object_uuid,
        1,
        claim.object_uuid,
        1,
        "has_claim",
        "owner",
    )
    repo.session.commit()
    return product, claim, relation


class RecordingAdapter:
    def __init__(self, mutate=None):
        self.calls = []
        self.mutate = mutate

    def apply(self, batch: GraphSyncBatch) -> GraphSyncResult:
        self.calls.append(batch)
        payload = {
            "adapter_name": "recording",
            "batch_checksum_sha256": batch.canonical_checksum_sha256,
            "root": batch.graph.root,
            "depth": batch.graph.depth,
            "nodes_written": len(batch.graph.nodes),
            "edges_written": len(batch.graph.edges),
        }
        if self.mutate:
            self.mutate(payload)
        return GraphSyncResult(**payload)


def test_same_scope_produces_identical_canonical_sync_batch(repo):
    _, claim, _ = _context(repo)
    service = GraphSyncService(repo)

    first = service.build_batch(claim.uuid_hex, 1, depth=1)
    second = service.build_batch(claim.uuid_hex, 1, depth=1)

    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_checksum_sha256 == second.canonical_checksum_sha256
    assert first.graph.model_dump(mode="json") == second.graph.model_dump(mode="json")
    assert first.source_authority == "object_store"
    assert first.approval_authority == "object_store"
    assert first.read_only is True
    assert first.sync_mode == "replace_exact_scope"


def test_sync_batch_preserves_exact_versions_and_active_relations(repo):
    product, claim, relation = _context(repo)
    batch = GraphSyncService(repo).build_batch(claim.uuid_hex, 1, depth=1)

    assert {(node.object_uuid, node.object_version) for node in batch.graph.nodes} == {
        (product.uuid_hex, 1),
        (claim.uuid_hex, 1),
    }
    assert [edge.relation_uuid for edge in batch.graph.edges] == [
        UUID(bytes=relation.relation_uuid).hex
    ]
    assert batch.graph.edges[0].source.object_version == 1
    assert batch.graph.edges[0].target.object_version == 1


def test_historical_version_can_be_synchronized_as_independent_scope(repo):
    product, claim, _ = _context(repo)
    repo.create_version(
        claim.object_uuid,
        {
            "claim_type": "clinical",
            "claim_category": "clinical",
            "confidence": "high",
            "severity": "medium",
            "jurisdiction": "EU",
            "language": "en",
            "wording": "Sync claim v2",
            "regulatory_scope": [],
        },
        "claim-owner",
    )
    repo.session.commit()

    service = GraphSyncService(repo)
    v1 = service.build_batch(claim.uuid_hex, 1, depth=1)
    v2 = service.build_batch(claim.uuid_hex, 2, depth=1)

    assert v1.graph.root.object_version == 1
    assert {(node.object_uuid, node.object_version) for node in v1.graph.nodes} == {
        (product.uuid_hex, 1),
        (claim.uuid_hex, 1),
    }
    assert v2.graph.root.object_version == 2
    assert [(node.object_uuid, node.object_version) for node in v2.graph.nodes] == [
        (claim.uuid_hex, 2)
    ]
    assert v1.canonical_checksum_sha256 != v2.canonical_checksum_sha256


def test_sync_scope_invokes_adapter_without_mutating_object_store(repo):
    _, claim, _ = _context(repo)
    service = GraphSyncService(repo)
    adapter = RecordingAdapter()
    events_before = len(repo.get_event_history(claim.object_uuid))
    version_before = claim.current_version
    state_before = claim.lifecycle_state

    result = service.sync_scope(claim.uuid_hex, 1, adapter, depth=1)

    assert len(adapter.calls) == 1
    assert result.applied is True
    assert result.nodes_written == 2
    assert result.edges_written == 1
    assert len(repo.get_event_history(claim.object_uuid)) == events_before
    assert claim.current_version == version_before
    assert claim.lifecycle_state == state_before


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(batch_checksum_sha256="0" * 64),
        lambda payload: payload.update(depth=payload["depth"] + 1),
        lambda payload: payload.update(nodes_written=payload["nodes_written"] + 1),
        lambda payload: payload.update(edges_written=payload["edges_written"] + 1),
    ],
)
def test_sync_scope_rejects_adapter_acknowledgement_mismatch(repo, mutate):
    _, claim, _ = _context(repo)
    adapter = RecordingAdapter(mutate=mutate)

    with pytest.raises(
        GraphSynchronizationError, match="does not match submitted batch"
    ):
        GraphSyncService(repo).sync_scope(claim.uuid_hex, 1, adapter, depth=1)


def test_sync_batch_rejects_checksum_tampering(repo):
    _, claim, _ = _context(repo)
    batch = GraphSyncService(repo).build_batch(claim.uuid_hex, 1, depth=1)
    payload = deepcopy(batch.model_dump(mode="json"))
    payload["canonical_checksum_sha256"] = "0" * 64

    with pytest.raises(ValidationError, match="checksum does not match"):
        GraphSyncBatch(**payload)

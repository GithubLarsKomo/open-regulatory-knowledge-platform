"""Deterministic synchronization boundary for graph infrastructure adapters."""

from typing import Protocol

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import GraphSynchronizationError
from orkp.domain.graph_service import GraphProjectionService
from orkp.domain.graph_sync_models import GraphSyncBatch, GraphSyncResult


class GraphSyncAdapter(Protocol):
    """Infrastructure adapter that applies one canonical exact-scope graph batch."""

    def apply(self, batch: GraphSyncBatch) -> GraphSyncResult:
        """Apply the batch and return an acknowledgement of the exact payload."""
        ...


class GraphSyncService:
    """Build and validate deterministic sync batches from Object Store authority."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def build_batch(
        self,
        object_uuid: str,
        object_version: int,
        depth: int = 1,
    ) -> GraphSyncBatch:
        graph = GraphProjectionService(self.repo).traceability(
            object_uuid,
            object_version,
            depth,
        )
        return GraphSyncBatch.from_graph(graph)

    def sync_scope(
        self,
        object_uuid: str,
        object_version: int,
        adapter: GraphSyncAdapter,
        depth: int = 1,
    ) -> GraphSyncResult:
        batch = self.build_batch(object_uuid, object_version, depth)
        result = adapter.apply(batch)
        self._validate_result(batch, result)
        return result

    @staticmethod
    def _validate_result(batch: GraphSyncBatch, result: GraphSyncResult) -> None:
        expected = {
            "batch_checksum_sha256": batch.canonical_checksum_sha256,
            "root": batch.graph.root,
            "depth": batch.graph.depth,
            "nodes_written": len(batch.graph.nodes),
            "edges_written": len(batch.graph.edges),
        }
        actual = {
            "batch_checksum_sha256": result.batch_checksum_sha256,
            "root": result.root,
            "depth": result.depth,
            "nodes_written": result.nodes_written,
            "edges_written": result.edges_written,
        }
        if actual != expected:
            raise GraphSynchronizationError(
                "Graph synchronization adapter acknowledgement does not match submitted batch"
            )

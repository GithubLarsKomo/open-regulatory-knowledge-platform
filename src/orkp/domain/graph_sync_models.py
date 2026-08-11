"""Strict infrastructure-neutral models for deterministic graph synchronization."""

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from orkp.domain.graph_models import GraphObjectReference, TraceabilityGraph


class GraphSyncBatch(BaseModel):
    """Canonical exact-scope graph payload supplied to a synchronization adapter."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["graph-sync-batch-1.0"] = "graph-sync-batch-1.0"
    source_authority: Literal["object_store"] = "object_store"
    approval_authority: Literal["object_store"] = "object_store"
    read_only: Literal[True] = True
    sync_mode: Literal["replace_exact_scope"] = "replace_exact_scope"
    graph: TraceabilityGraph
    canonical_checksum_sha256: str = Field(..., min_length=64, max_length=64)

    @classmethod
    def from_graph(cls, graph: TraceabilityGraph) -> "GraphSyncBatch":
        checksum = cls._checksum_for_graph(graph)
        return cls(graph=graph, canonical_checksum_sha256=checksum)

    def canonical_json(self) -> str:
        return self._canonical_graph_json(self.graph)

    @model_validator(mode="after")
    def validate_checksum(self):
        expected = self._checksum_for_graph(self.graph)
        if self.canonical_checksum_sha256 != expected:
            raise ValueError("graph sync batch checksum does not match canonical payload")
        return self

    @classmethod
    def _checksum_for_graph(cls, graph: TraceabilityGraph) -> str:
        return hashlib.sha256(cls._canonical_graph_json(graph).encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_graph_json(graph: TraceabilityGraph) -> str:
        payload = {
            "schema_version": "graph-sync-batch-1.0",
            "source_authority": "object_store",
            "approval_authority": "object_store",
            "read_only": True,
            "sync_mode": "replace_exact_scope",
            "graph": graph.model_dump(mode="json"),
        }
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


class GraphSyncResult(BaseModel):
    """Adapter acknowledgement for one exact synchronization batch."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["graph-sync-result-1.0"] = "graph-sync-result-1.0"
    adapter_name: str = Field(..., min_length=1)
    batch_checksum_sha256: str = Field(..., min_length=64, max_length=64)
    root: GraphObjectReference
    depth: int = Field(..., ge=0, le=10)
    nodes_written: int = Field(..., ge=0)
    edges_written: int = Field(..., ge=0)
    applied: Literal[True] = True

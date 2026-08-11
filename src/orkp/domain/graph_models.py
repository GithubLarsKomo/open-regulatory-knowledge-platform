"""Strict models for version-aware regulatory traceability graph projection."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GraphObjectReference(BaseModel):
    """Exact object identity + version used as a graph endpoint."""

    model_config = ConfigDict(extra="forbid")

    object_uuid: str
    object_version: int = Field(..., ge=1)

    @field_validator("object_uuid")
    @classmethod
    def normalize_uuid(cls, value: str) -> str:
        try:
            return UUID(value).hex
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("object_uuid must be a valid UUID") from exc


class GraphNode(BaseModel):
    """Version-aware read model projected from Object Store authority."""

    model_config = ConfigDict(extra="forbid")

    object_uuid: str
    object_version: int = Field(..., ge=1)
    object_type: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    version_status: str = Field(..., min_length=1)
    current_lifecycle_state: str = Field(..., min_length=1)
    is_current_version: bool

    @field_validator("object_uuid")
    @classmethod
    def normalize_uuid(cls, value: str) -> str:
        try:
            return UUID(value).hex
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("object_uuid must be a valid UUID") from exc


class GraphEdge(BaseModel):
    """Exact active Object Store relationship projected into graph form."""

    model_config = ConfigDict(extra="forbid")

    relation_uuid: str
    relation_type: str = Field(..., min_length=1)
    source: GraphObjectReference
    target: GraphObjectReference
    properties: dict[str, Any] | None = None
    created_at: datetime

    @field_validator("relation_uuid")
    @classmethod
    def normalize_relation_uuid(cls, value: str) -> str:
        try:
            return UUID(value).hex
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("relation_uuid must be a valid UUID") from exc


class TraceabilityGraph(BaseModel):
    """Deterministic read-only graph slice rooted at an exact object version."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["traceability-graph-1.0"] = "traceability-graph-1.0"
    root: GraphObjectReference
    depth: int = Field(..., ge=0, le=10)
    approval_authority: Literal["object_store"] = "object_store"
    read_only: Literal[True] = True
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    @model_validator(mode="after")
    def validate_graph_contract(self):
        node_keys = [(node.object_uuid, node.object_version) for node in self.nodes]
        if len(node_keys) != len(set(node_keys)):
            raise ValueError("traceability graph must not contain duplicate nodes")
        edge_ids = [edge.relation_uuid for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("traceability graph must not contain duplicate edges")
        if (self.root.object_uuid, self.root.object_version) not in set(node_keys):
            raise ValueError("traceability graph must contain its root node")
        return self

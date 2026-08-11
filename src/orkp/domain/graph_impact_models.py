"""Strict models for deterministic version-aware graph impact analysis."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from orkp.domain.graph_models import GraphEdge, GraphNode, GraphObjectReference


class ImpactedObject(BaseModel):
    """An exact object version reached from a changed graph root."""

    model_config = ConfigDict(extra="forbid")

    node: GraphNode
    distance: int = Field(..., ge=1, le=10)
    path: list[GraphObjectReference] = Field(..., min_length=2)
    relation_path: list[str] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_path(self):
        if len(self.path) != self.distance + 1:
            raise ValueError("impact path length must match distance")
        if len(self.relation_path) != self.distance:
            raise ValueError("impact relation_path length must match distance")
        if self.path[-1].object_uuid != self.node.object_uuid or (
            self.path[-1].object_version != self.node.object_version
        ):
            raise ValueError("impact path must terminate at impacted node")
        return self


class ImpactAnalysis(BaseModel):
    """Conservative read-only change-impact analysis for one exact object version."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["impact-analysis-1.0"] = "impact-analysis-1.0"
    changed: GraphObjectReference
    depth: int = Field(..., ge=1, le=10)
    approval_authority: Literal["object_store"] = "object_store"
    read_only: Literal[True] = True
    propagation_policy: Literal["bidirectional_active_relations"] = (
        "bidirectional_active_relations"
    )
    impacted: list[ImpactedObject]
    edges: list[GraphEdge]

    @model_validator(mode="after")
    def validate_contract(self):
        keys = [
            (item.node.object_uuid, item.node.object_version) for item in self.impacted
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("impact analysis must not contain duplicate impacted nodes")
        edge_ids = [edge.relation_uuid for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("impact analysis must not contain duplicate edges")
        changed_key = (self.changed.object_uuid, self.changed.object_version)
        if changed_key in set(keys):
            raise ValueError("changed root must not be repeated as an impacted node")
        return self

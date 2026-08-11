"""Strict models for deterministic version-aware graph impact analysis."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orkp.domain.graph_models import GraphEdge, GraphNode, GraphObjectReference


class ImpactedObject(BaseModel):
    """An exact object version reached from a changed graph root."""

    model_config = ConfigDict(extra="forbid")

    node: GraphNode
    distance: int = Field(..., ge=1, le=10)
    path: list[GraphObjectReference] = Field(..., min_length=2)
    relation_path: list[str] = Field(..., min_length=1)

    @field_validator("relation_path")
    @classmethod
    def normalize_relation_path(cls, value: list[str]) -> list[str]:
        normalized = []
        for relation_uuid in value:
            try:
                normalized.append(UUID(relation_uuid).hex)
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValueError("relation_path must contain valid UUIDs") from exc
        return normalized

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
            raise ValueError(
                "impact analysis must not contain duplicate impacted nodes"
            )

        edge_ids = [edge.relation_uuid for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("impact analysis must not contain duplicate edges")
        edge_map = {edge.relation_uuid: edge for edge in self.edges}

        changed_key = (self.changed.object_uuid, self.changed.object_version)
        impacted_keys = set(keys)
        if changed_key in impacted_keys:
            raise ValueError("changed root must not be repeated as an impacted node")

        allowed_keys = impacted_keys | {changed_key}
        for edge in self.edges:
            source_key = (edge.source.object_uuid, edge.source.object_version)
            target_key = (edge.target.object_uuid, edge.target.object_version)
            if source_key not in allowed_keys or target_key not in allowed_keys:
                raise ValueError(
                    "impact edge endpoints must be present in changed/impacted nodes"
                )

        for item in self.impacted:
            if item.distance > self.depth:
                raise ValueError("impacted node distance exceeds analysis depth")
            first_key = (item.path[0].object_uuid, item.path[0].object_version)
            if first_key != changed_key:
                raise ValueError("impact path must start at changed root")

            for index, relation_uuid in enumerate(item.relation_path):
                edge = edge_map.get(relation_uuid)
                if edge is None:
                    raise ValueError("impact relation_path references an unknown edge")
                current_key = (
                    item.path[index].object_uuid,
                    item.path[index].object_version,
                )
                next_key = (
                    item.path[index + 1].object_uuid,
                    item.path[index + 1].object_version,
                )
                source_key = (edge.source.object_uuid, edge.source.object_version)
                target_key = (edge.target.object_uuid, edge.target.object_version)
                if {current_key, next_key} != {source_key, target_key}:
                    raise ValueError(
                        "impact relation_path edge does not connect adjacent path nodes"
                    )
        return self

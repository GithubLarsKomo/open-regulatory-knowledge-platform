"""Read-only version-aware traceability graph projection from the Object Store."""

from collections import deque
from uuid import UUID

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    InvalidObjectIdentifierError,
    ObjectNotFoundError,
    ObjectVersionNotFoundError,
)
from orkp.domain.graph_impact_models import ImpactAnalysis, ImpactedObject
from orkp.domain.graph_models import (
    GraphEdge,
    GraphNode,
    GraphObjectReference,
    TraceabilityGraph,
)


_LABEL_FIELDS = (
    "name",
    "title",
    "wording",
    "product_id",
    "device_id",
    "claim_id",
    "study_id",
    "result_id",
    "risk_id",
    "hazard_id",
    "control_id",
    "requirement_id",
    "evidence_id",
    "analysis_id",
    "assessment_id",
    "information_id",
    "report_type",
)


class GraphProjectionService:
    """Project exact Object Store versions and active relations into graph form."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def traceability(
        self,
        object_uuid: str,
        object_version: int,
        depth: int = 1,
    ) -> TraceabilityGraph:
        root_uuid = self._parse_uuid(object_uuid)
        if object_version < 1:
            raise ObjectVersionNotFoundError(
                f"Object version must be >= 1, got {object_version}"
            )
        if depth < 0 or depth > 10:
            raise InvalidObjectIdentifierError(
                "Graph traversal depth must be between 0 and 10"
            )

        self._load_node(root_uuid, object_version)

        queue = deque([(root_uuid, object_version, 0)])
        visited: set[tuple[bytes, int]] = set()
        nodes: dict[tuple[bytes, int], GraphNode] = {}
        edges: dict[bytes, GraphEdge] = {}

        while queue:
            current_uuid, current_version, level = queue.popleft()
            current_key = (current_uuid, current_version)
            if current_key in visited:
                continue
            visited.add(current_key)
            nodes[current_key] = self._load_node(current_uuid, current_version)

            if level >= depth:
                continue

            relations = self._relations_for_exact_version(current_uuid, current_version)
            for relation in relations:
                edges[relation.relation_uuid] = self._project_edge(relation)
                if (
                    relation.source_uuid == current_uuid
                    and relation.source_version == current_version
                ):
                    adjacent = (relation.target_uuid, relation.target_version)
                else:
                    adjacent = (relation.source_uuid, relation.source_version)
                if adjacent not in visited:
                    queue.append((*adjacent, level + 1))

        sorted_nodes = sorted(
            nodes.values(),
            key=lambda node: (node.object_type, node.object_uuid, node.object_version),
        )
        sorted_edges = sorted(
            edges.values(),
            key=lambda edge: (
                edge.relation_type,
                edge.source.object_uuid,
                edge.source.object_version,
                edge.target.object_uuid,
                edge.target.object_version,
                edge.relation_uuid,
            ),
        )
        return TraceabilityGraph(
            root=GraphObjectReference(
                object_uuid=UUID(bytes=root_uuid).hex,
                object_version=object_version,
            ),
            depth=depth,
            nodes=sorted_nodes,
            edges=sorted_edges,
        )

    def impact_analysis(
        self,
        object_uuid: str,
        object_version: int,
        depth: int = 2,
    ) -> ImpactAnalysis:
        """Return conservative exact-version change impact using graph connectivity.

        This deliberately does not infer regulatory causality from relation names.
        Any exact-version node reachable through active relations is considered
        potentially impacted and is returned with one deterministic shortest path.
        """
        if depth < 1 or depth > 10:
            raise InvalidObjectIdentifierError(
                "Impact analysis depth must be between 1 and 10"
            )

        graph = self.traceability(object_uuid, object_version, depth)
        root_key = (graph.root.object_uuid, graph.root.object_version)
        nodes = {(node.object_uuid, node.object_version): node for node in graph.nodes}

        adjacency: dict[
            tuple[str, int], list[tuple[tuple[str, int], GraphEdge]]
        ] = {key: [] for key in nodes}
        for edge in graph.edges:
            source_key = (edge.source.object_uuid, edge.source.object_version)
            target_key = (edge.target.object_uuid, edge.target.object_version)
            adjacency.setdefault(source_key, []).append((target_key, edge))
            adjacency.setdefault(target_key, []).append((source_key, edge))

        for neighbors in adjacency.values():
            neighbors.sort(
                key=lambda item: (
                    item[1].relation_type,
                    item[0][0],
                    item[0][1],
                    item[1].relation_uuid,
                )
            )

        distances: dict[tuple[str, int], int] = {root_key: 0}
        parents: dict[
            tuple[str, int], tuple[tuple[str, int], GraphEdge]
        ] = {}
        queue = deque([root_key])

        while queue:
            current = queue.popleft()
            current_distance = distances[current]
            if current_distance >= depth:
                continue
            for adjacent, edge in adjacency.get(current, []):
                if adjacent in distances:
                    continue
                distances[adjacent] = current_distance + 1
                parents[adjacent] = (current, edge)
                queue.append(adjacent)

        impacted: list[ImpactedObject] = []
        for key, distance in distances.items():
            if key == root_key:
                continue
            path_keys = [key]
            relation_ids: list[str] = []
            cursor = key
            while cursor != root_key:
                parent, edge = parents[cursor]
                relation_ids.append(edge.relation_uuid)
                path_keys.append(parent)
                cursor = parent
            path_keys.reverse()
            relation_ids.reverse()
            impacted.append(
                ImpactedObject(
                    node=nodes[key],
                    distance=distance,
                    path=[
                        GraphObjectReference(
                            object_uuid=path_uuid,
                            object_version=path_version,
                        )
                        for path_uuid, path_version in path_keys
                    ],
                    relation_path=relation_ids,
                )
            )

        impacted.sort(
            key=lambda item: (
                item.distance,
                item.node.object_type,
                item.node.object_uuid,
                item.node.object_version,
            )
        )
        return ImpactAnalysis(
            changed=graph.root,
            depth=depth,
            impacted=impacted,
            edges=graph.edges,
        )

    def _relations_for_exact_version(self, object_uuid: bytes, version: int):
        by_uuid = {}
        for relation in self.repo.list_active_relations_for_source(object_uuid):
            if relation.source_version == version:
                by_uuid[relation.relation_uuid] = relation
        for relation in self.repo.list_active_relations_for_target(object_uuid):
            if relation.target_version == version:
                by_uuid[relation.relation_uuid] = relation
        return sorted(
            by_uuid.values(),
            key=lambda relation: (
                relation.relation_type,
                UUID(bytes=relation.source_uuid).hex,
                relation.source_version,
                UUID(bytes=relation.target_uuid).hex,
                relation.target_version,
                UUID(bytes=relation.relation_uuid).hex,
            ),
        )

    def _load_node(self, object_uuid: bytes, object_version: int) -> GraphNode:
        obj = self.repo.get_by_uuid_including_deleted(object_uuid)
        if obj is None:
            raise ObjectNotFoundError(
                f"Object {UUID(bytes=object_uuid).hex} not found"
            )
        version = self.repo.get_version(object_uuid, object_version)
        if version is None:
            raise ObjectVersionNotFoundError(
                f"Version {object_version} of object {UUID(bytes=object_uuid).hex} not found"
            )
        return GraphNode(
            object_uuid=UUID(bytes=object_uuid).hex,
            object_version=object_version,
            object_type=obj.object_type,
            label=self._label_for(
                obj.object_type,
                object_uuid,
                object_version,
                version.payload_json,
            ),
            version_status=version.status,
            current_lifecycle_state=obj.lifecycle_state,
            is_current_version=obj.current_version == object_version,
        )

    @staticmethod
    def _project_edge(relation) -> GraphEdge:
        return GraphEdge(
            relation_uuid=UUID(bytes=relation.relation_uuid).hex,
            relation_type=relation.relation_type,
            source=GraphObjectReference(
                object_uuid=UUID(bytes=relation.source_uuid).hex,
                object_version=relation.source_version,
            ),
            target=GraphObjectReference(
                object_uuid=UUID(bytes=relation.target_uuid).hex,
                object_version=relation.target_version,
            ),
            properties=dict(relation.properties) if relation.properties else None,
            created_at=relation.created_at,
        )

    @staticmethod
    def _label_for(
        object_type: str,
        object_uuid: bytes,
        object_version: int,
        payload: dict,
    ) -> str:
        for field in _LABEL_FIELDS:
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return f"{object_type}:{UUID(bytes=object_uuid).hex[:8]}:v{object_version}"

    @staticmethod
    def _parse_uuid(value: str) -> bytes:
        try:
            return UUID(value).bytes
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidObjectIdentifierError(f"Invalid object UUID: {value}") from exc

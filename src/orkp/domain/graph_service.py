"""Read-only version-aware traceability graph projection from the Object Store."""

from collections import deque
from uuid import UUID

from orkp.db.graph_read_repository import GraphReadRepository
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
        self.graph_reads = GraphReadRepository(repo.session)

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

        root_key = (root_uuid, object_version)
        nodes: dict[tuple[bytes, int], GraphNode] = {
            root_key: self._load_node(root_uuid, object_version)
        }
        edges: dict[bytes, GraphEdge] = {}
        discovered: set[tuple[bytes, int]] = {root_key}
        frontier: set[tuple[bytes, int]] = {root_key}

        for _level in range(depth):
            if not frontier:
                break

            relations = self.graph_reads.list_active_relations_for_version_pairs(
                frontier
            )
            next_frontier: set[tuple[bytes, int]] = set()

            for relation in relations:
                source_key = (relation.source_uuid, relation.source_version)
                target_key = (relation.target_uuid, relation.target_version)
                source_in_frontier = source_key in frontier
                target_in_frontier = target_key in frontier
                if not source_in_frontier and not target_in_frontier:
                    continue

                edges[relation.relation_uuid] = self._project_edge(relation)
                if source_in_frontier and target_key not in discovered:
                    next_frontier.add(target_key)
                if target_in_frontier and source_key not in discovered:
                    next_frontier.add(source_key)

            discovered.update(next_frontier)
            frontier = next_frontier

        non_root = discovered - {root_key}
        contexts = self.graph_reads.get_object_version_contexts(non_root)
        for node_key in non_root:
            context = contexts.get(node_key)
            if context is None:
                nodes[node_key] = self._load_node(*node_key)
                continue
            version, obj = context
            nodes[node_key] = self._project_node(obj, version)

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

        adjacency: dict[tuple[str, int], list[tuple[tuple[str, int], GraphEdge]]] = {
            key: [] for key in nodes
        }
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
        parents: dict[tuple[str, int], tuple[tuple[str, int], GraphEdge]] = {}
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

    def _load_node(self, object_uuid: bytes, object_version: int) -> GraphNode:
        obj, version = self.graph_reads.get_object_version_context(
            object_uuid, object_version
        )
        if obj is None:
            raise ObjectNotFoundError(f"Object {UUID(bytes=object_uuid).hex} not found")
        if version is None:
            raise ObjectVersionNotFoundError(
                f"Version {object_version} of object {UUID(bytes=object_uuid).hex} not found"
            )
        return self._project_node(obj, version)

    def _project_node(self, obj, version) -> GraphNode:
        return GraphNode(
            object_uuid=UUID(bytes=obj.object_uuid).hex,
            object_version=version.version_no,
            object_type=obj.object_type,
            label=self._label_for(
                obj.object_type,
                obj.object_uuid,
                version.version_no,
                version.payload_json,
            ),
            version_status=version.status,
            current_lifecycle_state=obj.lifecycle_state,
            is_current_version=obj.current_version == version.version_no,
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

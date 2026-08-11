"""Neo4j materialization adapter for canonical ORKP graph synchronization batches."""

import json
from typing import Any

from orkp.domain.exceptions import GraphSynchronizationError
from orkp.domain.graph_sync_models import GraphSyncBatch, GraphSyncResult


_OBJECT_CONSTRAINT = """
CREATE CONSTRAINT orkp_object_version_identity IF NOT EXISTS
FOR (n:ORKPObjectVersion)
REQUIRE (n.object_uuid, n.object_version) IS UNIQUE
""".strip()

_SCOPE_CONSTRAINT = """
CREATE CONSTRAINT orkp_sync_scope_key IF NOT EXISTS
FOR (s:ORKPSyncScope)
REQUIRE s.scope_key IS UNIQUE
""".strip()

_RELATION_CONSTRAINT = """
CREATE CONSTRAINT orkp_relation_uuid IF NOT EXISTS
FOR ()-[r:ORKP_RELATION]-()
REQUIRE r.relation_uuid IS UNIQUE
""".strip()

_REMOVE_OLD_RELATION_SCOPE = """
MATCH ()-[r:ORKP_RELATION]-()
WHERE $scope_key IN coalesce(r.scope_keys, [])
SET r.scope_keys = [key IN r.scope_keys WHERE key <> $scope_key]
""".strip()

_REMOVE_OLD_NODE_SCOPE = """
MATCH (n:ORKPObjectVersion)
WHERE $scope_key IN coalesce(n.scope_keys, [])
SET n.scope_keys = [key IN n.scope_keys WHERE key <> $scope_key]
""".strip()

_UPSERT_SCOPE = """
MERGE (scope:ORKPSyncScope {scope_key: $scope_key})
SET scope.root_object_uuid = $root_object_uuid,
    scope.root_object_version = $root_object_version,
    scope.depth = $depth,
    scope.batch_checksum_sha256 = $batch_checksum_sha256,
    scope.node_count = $node_count,
    scope.edge_count = $edge_count
""".strip()

_UPSERT_NODES = """
UNWIND $nodes AS item
MERGE (n:ORKPObjectVersion {
    object_uuid: item.object_uuid,
    object_version: item.object_version
})
SET n.object_type = item.object_type,
    n.label = item.label,
    n.version_status = item.version_status,
    n.current_lifecycle_state = item.current_lifecycle_state,
    n.is_current_version = item.is_current_version,
    n.scope_keys = CASE
        WHEN $scope_key IN coalesce(n.scope_keys, []) THEN n.scope_keys
        ELSE coalesce(n.scope_keys, []) + $scope_key
    END
""".strip()

_UPSERT_RELATIONS = """
UNWIND $edges AS item
MATCH (source:ORKPObjectVersion {
    object_uuid: item.source_object_uuid,
    object_version: item.source_object_version
})
MATCH (target:ORKPObjectVersion {
    object_uuid: item.target_object_uuid,
    object_version: item.target_object_version
})
MERGE (source)-[r:ORKP_RELATION {relation_uuid: item.relation_uuid}]->(target)
SET r.relation_type = item.relation_type,
    r.properties_json = item.properties_json,
    r.created_at = item.created_at,
    r.scope_keys = CASE
        WHEN $scope_key IN coalesce(r.scope_keys, []) THEN r.scope_keys
        ELSE coalesce(r.scope_keys, []) + $scope_key
    END
""".strip()

_DELETE_UNUSED_RELATIONS = """
MATCH ()-[r:ORKP_RELATION]-()
WHERE size(coalesce(r.scope_keys, [])) = 0
DELETE r
""".strip()

_DELETE_UNUSED_NODES = """
MATCH (n:ORKPObjectVersion)
WHERE size(coalesce(n.scope_keys, [])) = 0
DELETE n
""".strip()

_SCHEMA_QUERIES = (_OBJECT_CONSTRAINT, _SCOPE_CONSTRAINT, _RELATION_CONSTRAINT)


class Neo4jGraphSyncAdapter:
    """Materialize exact ORKP graph scopes into Neo4j as a derived read model."""

    adapter_name = "neo4j"

    def __init__(self, driver: Any, database: str = "neo4j"):
        if not database.strip():
            raise ValueError("database must not be blank")
        self.driver = driver
        self.database = database.strip()

    def ensure_schema(self) -> None:
        """Create idempotent Community-compatible uniqueness constraints."""
        try:
            for query in _SCHEMA_QUERIES:
                self.driver.execute_query(query, database_=self.database)
        except Exception as exc:
            raise GraphSynchronizationError(
                f"Neo4j graph schema initialization failed: {exc}"
            ) from exc

    def apply(self, batch: GraphSyncBatch) -> GraphSyncResult:
        """Replace one exact synchronized scope atomically and acknowledge the batch."""
        self.ensure_schema()
        scope_key = self.scope_key(batch)
        try:
            with self.driver.session(database=self.database) as session:
                session.execute_write(self._replace_scope, batch, scope_key)
        except GraphSynchronizationError:
            raise
        except Exception as exc:
            raise GraphSynchronizationError(
                f"Neo4j graph synchronization failed: {exc}"
            ) from exc

        return GraphSyncResult(
            adapter_name=self.adapter_name,
            batch_checksum_sha256=batch.canonical_checksum_sha256,
            root=batch.graph.root,
            depth=batch.graph.depth,
            nodes_written=len(batch.graph.nodes),
            edges_written=len(batch.graph.edges),
        )

    @staticmethod
    def scope_key(batch: GraphSyncBatch) -> str:
        root = batch.graph.root
        return f"{root.object_uuid}:v{root.object_version}:d{batch.graph.depth}"

    @classmethod
    def _replace_scope(cls, tx: Any, batch: GraphSyncBatch, scope_key: str) -> None:
        nodes = [
            {
                "object_uuid": node.object_uuid,
                "object_version": node.object_version,
                "object_type": node.object_type,
                "label": node.label,
                "version_status": node.version_status,
                "current_lifecycle_state": node.current_lifecycle_state,
                "is_current_version": node.is_current_version,
            }
            for node in batch.graph.nodes
        ]
        edges = [
            {
                "relation_uuid": edge.relation_uuid,
                "relation_type": edge.relation_type,
                "source_object_uuid": edge.source.object_uuid,
                "source_object_version": edge.source.object_version,
                "target_object_uuid": edge.target.object_uuid,
                "target_object_version": edge.target.object_version,
                "properties_json": cls._canonical_properties_json(edge.properties),
                "created_at": edge.created_at.isoformat(),
            }
            for edge in batch.graph.edges
        ]

        tx.run(_REMOVE_OLD_RELATION_SCOPE, scope_key=scope_key).consume()
        tx.run(_REMOVE_OLD_NODE_SCOPE, scope_key=scope_key).consume()
        tx.run(
            _UPSERT_SCOPE,
            scope_key=scope_key,
            root_object_uuid=batch.graph.root.object_uuid,
            root_object_version=batch.graph.root.object_version,
            depth=batch.graph.depth,
            batch_checksum_sha256=batch.canonical_checksum_sha256,
            node_count=len(nodes),
            edge_count=len(edges),
        ).consume()
        tx.run(_UPSERT_NODES, scope_key=scope_key, nodes=nodes).consume()
        tx.run(_UPSERT_RELATIONS, scope_key=scope_key, edges=edges).consume()
        tx.run(_DELETE_UNUSED_RELATIONS).consume()
        tx.run(_DELETE_UNUSED_NODES).consume()

    @staticmethod
    def _canonical_properties_json(properties: dict[str, Any] | None) -> str | None:
        if properties is None:
            return None
        return json.dumps(
            properties,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


def create_neo4j_driver(uri: str, username: str, password: str, **kwargs: Any):
    """Create the optional official Neo4j driver without making it a core dependency."""
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise RuntimeError(
            "Neo4j support is optional; install the project with the 'graph' extra"
        ) from exc
    return GraphDatabase.driver(uri, auth=(username, password), **kwargs)

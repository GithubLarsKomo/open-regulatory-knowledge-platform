"""Opt-in live Neo4j integration regressions for the graph materialization adapter.

These tests require a reachable Neo4j instance and are skipped by default.
Set ORKP_NEO4J_URI, ORKP_NEO4J_USERNAME and ORKP_NEO4J_PASSWORD to enable them.
"""

import os

import pytest

from orkp.domain.graph_models import (
    GraphEdge,
    GraphNode,
    GraphObjectReference,
    TraceabilityGraph,
)
from orkp.domain.graph_sync_models import GraphSyncBatch
from orkp.infrastructure.neo4j_graph_adapter import (
    Neo4jGraphSyncAdapter,
    create_neo4j_driver,
)


pytestmark = pytest.mark.integration


def _neo4j_config():
    uri = os.getenv("ORKP_NEO4J_URI")
    username = os.getenv("ORKP_NEO4J_USERNAME")
    password = os.getenv("ORKP_NEO4J_PASSWORD")
    if not all((uri, username, password)):
        pytest.skip("live Neo4j integration environment is not configured")
    return uri, username, password, os.getenv("ORKP_NEO4J_DATABASE", "neo4j")


def _batch(root_version: int = 1, include_edge: bool = True):
    product = GraphNode(
        object_uuid="10000000-0000-0000-0000-000000000001",
        object_version=1,
        object_type="product",
        label="Integration Product",
        version_status="approved",
        current_lifecycle_state="approved",
        is_current_version=True,
    )
    claim = GraphNode(
        object_uuid="10000000-0000-0000-0000-000000000002",
        object_version=root_version,
        object_type="claim",
        label=f"Integration Claim v{root_version}",
        version_status="approved",
        current_lifecycle_state="approved",
        is_current_version=True,
    )
    edges = []
    if include_edge:
        edges.append(
            GraphEdge(
                relation_uuid="10000000-0000-0000-0000-000000000003",
                relation_type="has_claim",
                source=GraphObjectReference(
                    object_uuid=product.object_uuid,
                    object_version=1,
                ),
                target=GraphObjectReference(
                    object_uuid=claim.object_uuid,
                    object_version=root_version,
                ),
                properties={"source": "live-integration"},
                created_at="2026-08-14T00:00:00Z",
            )
        )
    graph = TraceabilityGraph(
        root=GraphObjectReference(
            object_uuid=claim.object_uuid,
            object_version=root_version,
        ),
        depth=1,
        nodes=[product, claim],
        edges=edges,
    )
    return GraphSyncBatch.from_graph(graph)


def _cleanup(driver, database: str):
    driver.execute_query(
        "MATCH (n:ORKPObjectVersion) "
        "WHERE n.object_uuid STARTS WITH '10000000' DETACH DELETE n",
        database_=database,
    )
    driver.execute_query(
        "MATCH (s:ORKPSyncScope) "
        "WHERE s.root_object_uuid STARTS WITH '10000000' DELETE s",
        database_=database,
    )


def test_live_adapter_replaces_exact_scope_and_preserves_shared_scope_membership():
    uri, username, password, database = _neo4j_config()
    driver = create_neo4j_driver(uri, username, password)
    adapter = Neo4jGraphSyncAdapter(driver, database=database)
    try:
        _cleanup(driver, database)

        first = _batch(root_version=1, include_edge=True)
        adapter.apply(first)

        second = _batch(root_version=2, include_edge=False)
        adapter.apply(second)

        adapter.apply(_batch(root_version=1, include_edge=False))

        records, _, _ = driver.execute_query(
            "MATCH (n:ORKPObjectVersion) "
            "WHERE n.object_uuid = $product_uuid "
            "RETURN n.object_version AS version, n.scope_keys AS scope_keys",
            product_uuid="10000000000000000000000000000001",
            database_=database,
        )
        assert len(records) == 1
        assert records[0]["version"] == 1
        assert len(records[0]["scope_keys"]) == 2

        relation_records, _, _ = driver.execute_query(
            "MATCH ()-[r:ORKP_RELATION]-() "
            "WHERE r.relation_uuid = $relation_uuid RETURN count(r) AS count",
            relation_uuid="10000000000000000000000000000003",
            database_=database,
        )
        assert relation_records[0]["count"] == 0
    finally:
        try:
            _cleanup(driver, database)
        finally:
            driver.close()

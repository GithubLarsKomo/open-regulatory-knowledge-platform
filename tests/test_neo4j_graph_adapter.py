"""Unit regressions for the optional Neo4j exact-scope graph adapter."""

import json

import pytest

from orkp.domain.exceptions import GraphSynchronizationError
from orkp.domain.graph_models import (
    GraphEdge,
    GraphNode,
    GraphObjectReference,
    TraceabilityGraph,
)
from orkp.domain.graph_sync_models import GraphSyncBatch
from orkp.infrastructure.neo4j_graph_adapter import Neo4jGraphSyncAdapter


class FakeResult:
    def consume(self):
        return self


class FakeTransaction:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        if self.fail_at == len(self.calls):
            raise RuntimeError("transaction failure")
        return FakeResult()


class FakeSession:
    def __init__(self, driver):
        self.driver = driver

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute_write(self, callback, *args):
        self.driver.write_calls.append((callback, args))
        return callback(self.driver.transaction, *args)


class FakeDriver:
    def __init__(self, fail_schema=False, fail_at=None):
        self.schema_calls = []
        self.session_databases = []
        self.write_calls = []
        self.transaction = FakeTransaction(fail_at=fail_at)
        self.fail_schema = fail_schema

    def execute_query(self, query, **kwargs):
        self.schema_calls.append((query, kwargs))
        if self.fail_schema:
            raise RuntimeError("schema failure")
        return object()

    def session(self, *, database):
        self.session_databases.append(database)
        return FakeSession(self)


def _batch(properties=None):
    product = GraphNode(
        object_uuid="00000000-0000-0000-0000-000000000001",
        object_version=1,
        object_type="product",
        label="Product",
        version_status="draft",
        current_lifecycle_state="draft",
        is_current_version=True,
    )
    claim = GraphNode(
        object_uuid="00000000-0000-0000-0000-000000000002",
        object_version=2,
        object_type="claim",
        label="Claim v2",
        version_status="approved",
        current_lifecycle_state="approved",
        is_current_version=True,
    )
    edge = GraphEdge(
        relation_uuid="00000000-0000-0000-0000-000000000003",
        relation_type="has_claim",
        source=GraphObjectReference(
            object_uuid=product.object_uuid,
            object_version=product.object_version,
        ),
        target=GraphObjectReference(
            object_uuid=claim.object_uuid,
            object_version=claim.object_version,
        ),
        properties=properties,
        created_at="2026-08-11T20:00:00Z",
    )
    graph = TraceabilityGraph(
        root=GraphObjectReference(
            object_uuid=claim.object_uuid,
            object_version=claim.object_version,
        ),
        depth=1,
        nodes=[product, claim],
        edges=[edge],
    )
    return GraphSyncBatch.from_graph(graph)


def test_adapter_creates_community_compatible_uniqueness_constraints():
    driver = FakeDriver()
    adapter = Neo4jGraphSyncAdapter(driver, database="orkp")

    adapter.ensure_schema()

    assert len(driver.schema_calls) == 3
    assert all(call[1] == {"database_": "orkp"} for call in driver.schema_calls)
    queries = [call[0] for call in driver.schema_calls]
    assert any(
        "(n.object_uuid, n.object_version) IS UNIQUE" in query for query in queries
    )
    assert any("s.scope_key IS UNIQUE" in query for query in queries)
    assert any("r.relation_uuid IS UNIQUE" in query for query in queries)
    assert all("IF NOT EXISTS" in query for query in queries)


def test_apply_uses_one_explicit_write_transaction_and_exact_acknowledgement():
    driver = FakeDriver()
    adapter = Neo4jGraphSyncAdapter(driver, database="orkp")
    batch = _batch()

    result = adapter.apply(batch)

    assert driver.session_databases == ["orkp"]
    assert len(driver.write_calls) == 1
    assert len(driver.transaction.calls) == 7
    assert result.adapter_name == "neo4j"
    assert result.batch_checksum_sha256 == batch.canonical_checksum_sha256
    assert result.root == batch.graph.root
    assert result.depth == batch.graph.depth
    assert result.nodes_written == 2
    assert result.edges_written == 1


def test_replace_scope_removes_only_membership_then_upserts_and_cleans_unused():
    driver = FakeDriver()
    batch = _batch()

    Neo4jGraphSyncAdapter(driver).apply(batch)

    queries = [query for query, _ in driver.transaction.calls]
    assert (
        "SET r.scope_keys = [key IN r.scope_keys WHERE key <> $scope_key]" in queries[0]
    )
    assert (
        "SET n.scope_keys = [key IN n.scope_keys WHERE key <> $scope_key]" in queries[1]
    )
    assert "MERGE (scope:ORKPSyncScope" in queries[2]
    assert "UNWIND $nodes AS item" in queries[3]
    assert "UNWIND $edges AS item" in queries[4]
    assert "DELETE r" in queries[5]
    assert "DELETE n" in queries[6]
    assert "DETACH DELETE" not in queries[6]


def test_adapter_preserves_exact_versions_and_uses_static_graph_identifiers():
    driver = FakeDriver()
    batch = _batch()

    Neo4jGraphSyncAdapter(driver).apply(batch)

    node_params = driver.transaction.calls[3][1]
    edge_params = driver.transaction.calls[4][1]
    assert {
        (item["object_uuid"], item["object_version"]) for item in node_params["nodes"]
    } == {
        ("00000000000000000000000000000001", 1),
        ("00000000000000000000000000000002", 2),
    }
    assert edge_params["edges"][0]["source_object_version"] == 1
    assert edge_params["edges"][0]["target_object_version"] == 2
    relation_query = driver.transaction.calls[4][0]
    assert ":ORKP_RELATION" in relation_query
    assert "has_claim" not in relation_query
    assert "claim" not in relation_query


def test_relation_metadata_is_serialized_as_deterministic_json():
    driver = FakeDriver()
    batch = _batch(properties={"z": [2, 1], "a": {"nested": True}})

    Neo4jGraphSyncAdapter(driver).apply(batch)

    serialized = driver.transaction.calls[4][1]["edges"][0]["properties_json"]
    assert serialized == json.dumps(
        {"a": {"nested": True}, "z": [2, 1]},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def test_scope_key_is_stable_for_root_version_and_depth():
    batch = _batch()

    assert Neo4jGraphSyncAdapter.scope_key(batch) == (
        "00000000000000000000000000000002:v2:d1"
    )


def test_schema_failure_becomes_typed_graph_synchronization_error():
    adapter = Neo4jGraphSyncAdapter(FakeDriver(fail_schema=True))

    with pytest.raises(GraphSynchronizationError, match="schema initialization failed"):
        adapter.apply(_batch())


def test_transaction_failure_becomes_typed_graph_synchronization_error():
    adapter = Neo4jGraphSyncAdapter(FakeDriver(fail_at=4))

    with pytest.raises(GraphSynchronizationError, match="synchronization failed"):
        adapter.apply(_batch())


def test_blank_database_is_rejected_before_driver_use():
    with pytest.raises(ValueError, match="database must not be blank"):
        Neo4jGraphSyncAdapter(FakeDriver(), database="   ")

# Epic 008 — Knowledge Graph

## Status

In progress.

## Slice 1 — Canonical Versioned Traceability Projection

Issue: #27

Primary requirements:

- `GRAPH-CORE-0001` — traceability relationships between regulatory objects
- `GRAPH-CORE-0003` — object identity and object version are distinct
- `GRAPH-CORE-0004` — graph is not approval authority

### Boundary

The Object Store and Event Store remain authoritative. The graph layer is a read model.

This first slice intentionally does **not** claim Neo4j synchronization. `ADR-0003` identifies Neo4j as the reference graph database, but the repository currently has no Neo4j runtime dependency. The slice therefore establishes the canonical graph semantics that a later Neo4j adapter must materialize exactly.

### Canonical node identity

A graph node is identified by the pair:

`(object_uuid, object_version)`

The stable object UUID is not conflated with a particular version. A node also exposes:

- `object_type`
- deterministic display `label` from the exact version payload
- exact `version_status`
- current Object Store lifecycle state
- whether the represented version is the current object version

### Canonical edges

Each graph edge is projected from one active `object_relation` and preserves:

- exact `relation_uuid`
- `relation_type`
- exact source UUID/version
- exact target UUID/version
- relation properties
- relation creation timestamp

Inactive relations are not projected.

### Traceability query

`GraphProjectionService.traceability()` performs deterministic bounded traversal over incoming and outgoing active relations for an exact root object version.

REST:

`GET /api/v1/graph/objects/{object_uuid}/versions/{object_version}/traceability?depth=1`

Depth is bounded to 0..10. Output is duplicate-free and deterministically sorted.

## Slice 2 — Exact-Version Change Impact Analysis

Issue: #28

Primary requirement:

- `GRAPH-CORE-0002` — impact analysis after changes to claims, risks, evidence or requirements

### Impact boundary

Impact analysis reuses the canonical traceability projection. It does not maintain a second relation index or versioning model.

The changed root is always an exact `(object_uuid, object_version)`. Only active relations pinned to that exact version are considered. A later version of the same UUID is a different impact root unless an explicit versioned relation connects it.

The first impact policy is deliberately conservative:

`bidirectional_active_relations`

Any exact-version node reachable over active relations within the requested depth is reported as potentially impacted. This policy does **not** claim domain-specific causal semantics or automatic regulatory decisions.

For every impacted node, the response contains:

- exact impacted node/version
- graph distance from the changed root
- one deterministic shortest object-version path
- the exact relation UUID path supporting that impact path

The changed root itself is not repeated in the impacted list. Output is duplicate-free and deterministic.

REST:

`GET /api/v1/graph/objects/{object_uuid}/versions/{object_version}/impact?depth=2`

Depth is bounded to 1..10.

## Slice 3 — Deterministic Graph Synchronization Contract

Issue: #29

Before a concrete Neo4j driver is introduced, the platform defines the exact payload and acknowledgement contract an infrastructure adapter must obey.

`GraphSyncService.build_batch()` reuses `GraphProjectionService.traceability()` and wraps the resulting exact-version graph in `GraphSyncBatch`.

The batch contract is:

- schema `graph-sync-batch-1.0`
- `source_authority = "object_store"`
- `approval_authority = "object_store"`
- `read_only = true`
- `sync_mode = "replace_exact_scope"`
- one exact traceability root + depth
- deterministic canonical JSON
- SHA-256 over that canonical payload

`GraphSyncAdapter` is an infrastructure-neutral Protocol. A later Neo4j implementation receives the immutable batch and returns `GraphSyncResult`.

`GraphSyncService.sync_scope()` rejects an adapter acknowledgement unless all of these exactly match the submitted batch:

- batch checksum
- root UUID/version
- depth
- node count
- edge count

This prevents a graph adapter from silently reporting success for a different or partial regulatory graph scope.

No Object Store object, version, relation, lifecycle state or approval record is modified by synchronization.

## Governance

All graph query and synchronization contracts preserve the Object Store and Event Store as regulatory authority. Graph infrastructure is a derived read model and does not create approval authority.

Every graph query response explicitly declares:

- `approval_authority = "object_store"`
- `read_only = true`

The sync batch repeats the same authority boundary.

## Deferred slices

- concrete Neo4j driver/configuration
- Neo4j constraints/index creation
- event-driven/incremental synchronization and retry/outbox semantics
- RBAC graph filtering, which depends on Epic 010
- optional future relation-type-specific impact classification/weights; not required by current `GRAPH-CORE` requirements

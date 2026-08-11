# Epic 008 — Knowledge Graph

## Status

In progress.

## Slice 1 — Canonical Versioned Traceability Projection

Issue: #27 — completed.

Primary requirements:

- `GRAPH-CORE-0001` — traceability relationships between regulatory objects
- `GRAPH-CORE-0003` — object identity and object version are distinct
- `GRAPH-CORE-0004` — graph is not approval authority

The Object Store and Event Store remain authoritative. `GraphProjectionService.traceability()` exposes a deterministic read-only graph where node identity is `(object_uuid, object_version)` and edges preserve exact active Object Store relation UUID/type/source version/target version.

REST:

`GET /api/v1/graph/objects/{object_uuid}/versions/{object_version}/traceability?depth=1`

## Slice 2 — Exact-Version Change Impact Analysis

Issue: #28 — completed.

Primary requirement:

- `GRAPH-CORE-0002` — impact analysis after changes to claims, risks, evidence or requirements

Impact analysis reuses the canonical traceability projection. The changed root is always an exact `(object_uuid, object_version)`. The conservative baseline policy is `bidirectional_active_relations`; every reachable exact-version node within the requested depth is potentially impacted and carries one deterministic shortest supporting path.

REST:

`GET /api/v1/graph/objects/{object_uuid}/versions/{object_version}/impact?depth=2`

## Slice 3 — Deterministic Graph Synchronization Contract

Issue: #29 — completed.

`GraphSyncService.build_batch()` wraps the canonical traceability projection as `graph-sync-batch-1.0` with:

- Object Store source/approval authority;
- read-only regulatory semantics;
- `replace_exact_scope` mode;
- deterministic canonical JSON;
- SHA-256 checksum.

`GraphSyncAdapter` is infrastructure-neutral. `GraphSyncService.sync_scope()` rejects acknowledgements that do not exactly match submitted checksum, root UUID/version, depth, node count and edge count.

## Slice 4 — Neo4j Exact-Scope Materialization Adapter

Issue: #30

The optional `Neo4jGraphSyncAdapter` implements the synchronization contract using the official Neo4j Python driver 6.x when the project is installed with the `graph` extra. Core ORKP does not import Neo4j.

### Materialization schema

The adapter deliberately uses static infrastructure labels/types rather than dynamic regulatory identifiers:

- `:ORKPObjectVersion` — one node per exact `(object_uuid, object_version)`;
- `:ORKPSyncScope` — one node per stable `(root UUID, root version, depth)` scope key;
- `:ORKP_RELATION` — one relationship per canonical Object Store `relation_uuid`.

Original `object_type` and `relation_type` remain properties. This prevents regulatory data from being interpolated into Cypher identifiers.

Idempotent uniqueness constraints protect:

- composite object-version identity;
- scope key;
- relationship UUID.

These use property uniqueness constraints available in Neo4j Community Edition.

### Atomic `replace_exact_scope`

One `Session.execute_write()` transaction:

1. removes only the target scope key from previously materialized relationship memberships;
2. removes only the target scope key from previously materialized node memberships;
3. upserts the scope metadata/checksum;
4. upserts exact-version nodes and adds the scope membership;
5. upserts exact relation UUIDs and adds the scope membership;
6. deletes relationships with no remaining scope membership;
7. deletes nodes with no remaining scope membership.

Node cleanup intentionally uses `DELETE`, not `DETACH DELETE`: an unexpected remaining relationship makes synchronization fail instead of silently destroying shared graph data.

Relation metadata is stored as deterministic canonical JSON, avoiding unsupported/nested arbitrary Neo4j property structures.

Driver/schema/transaction failures become typed `GraphSynchronizationError` failures. The adapter acknowledgement is still validated by `GraphSyncService` against the canonical batch.

## Governance

All graph query and synchronization layers preserve the Object Store and Event Store as regulatory authority. Neo4j is a derived read model only and never becomes approval authority.

## Deferred slices

- live Neo4j integration/container verification;
- event-driven/incremental synchronization and retry/outbox semantics;
- operational connection/credential configuration;
- RBAC graph filtering, which depends on Epic 010;
- optional future relation-type-specific impact classification/weights; not required by current `GRAPH-CORE` requirements.

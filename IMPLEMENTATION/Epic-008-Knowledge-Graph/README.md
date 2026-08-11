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

### Governance

The graph endpoint is read-only. It does not create versions, relations, lifecycle transitions, approvals or graph-owned approval state.

Every response explicitly declares:

- `approval_authority = "object_store"`
- `read_only = true`

### Deferred slices

- Neo4j schema/constraints and synchronization adapter
- event-driven/incremental synchronization
- `GRAPH-CORE-0002` impact analysis
- RBAC graph filtering, which depends on Epic 010

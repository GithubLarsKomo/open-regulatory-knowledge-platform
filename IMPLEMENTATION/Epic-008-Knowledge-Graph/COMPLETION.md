# Epic 008 — Knowledge Graph — Completion Record

## Status

Epic 008 / `TASK-GRAPH-0001` is functionally complete for the normative `GRAPH-CORE-0001` through `GRAPH-CORE-0004` requirements.

The verified normal-development gate on the Neo4j adapter stack reported:

- `pytest -q`: **528 passed, 1 skipped, 1 warning**
- skipped test: opt-in live Neo4j integration verification because no live Neo4j environment variables were configured
- known warning: Starlette/httpx `TestClient` deprecation only
- `ruff check --select E9,F63,F7,F82 .`: **passed**
- strict spec linter: **35 files / 168 IDs / 0 duplicates / 0 invalid formats / 0 undefined references** before this completion record was added
- backlog generator: **5 foundation tasks / 14 generated tasks**
- `git diff --check`: only expected CRLF notices for generated Markdown artifacts
- working tree: clean after restoring generated lint report

The final Ruff-only drift in `tests/test_neo4j_graph_adapter.py` was applied on master in `0c72429`; it changed layout only and did not alter behavior.

## Requirements covered

### `GRAPH-CORE-0001` — Represent traceability relationships between regulatory objects

Implemented through strict graph read models and `GraphProjectionService.traceability()`.

Canonical graph semantics:

- node identity is exact `(object_uuid, object_version)`
- each graph edge preserves exact `relation_uuid`, `relation_type`, source UUID/version and target UUID/version
- only active Object Store relations are projected
- incoming and outgoing relations are traversed
- historical object versions remain queryable
- output is deterministic and duplicate-free

REST reference endpoint:

`GET /api/v1/graph/objects/{object_uuid}/versions/{object_version}/traceability?depth=1`

### `GRAPH-CORE-0002` — Support impact analysis after changes

Implemented through `GraphProjectionService.impact_analysis()` on top of the same exact-version traceability projection.

The baseline propagation policy is explicit and conservative:

`bidirectional_active_relations`

For every impacted exact-version node, the analysis returns:

- graph distance
- one deterministic shortest object-version path
- exact relation UUID path supporting the result

The impact payload validates that each path starts at the changed exact version, ends at the declared impacted node and uses only declared edges that actually connect adjacent path nodes.

REST reference endpoint:

`GET /api/v1/graph/objects/{object_uuid}/versions/{object_version}/impact?depth=2`

### `GRAPH-CORE-0003` — Distinguish object identity from object version

The graph never conflates a stable object UUID with one of its versions.

Examples covered by regressions:

- Claim v1 and Claim v2 are distinct graph nodes
- a relation pinned to Claim v1 is not silently treated as a relation to Claim v2
- historical versions can be roots for traceability, impact analysis and synchronization
- Neo4j materialization uniquely identifies `:ORKPObjectVersion` by `(object_uuid, object_version)`

### `GRAPH-CORE-0004` — Graph is not the primary approval record

Every graph read model declares:

- `approval_authority = "object_store"`
- `read_only = true`

Graph projection, impact analysis and synchronization never create Object Store versions, relations, lifecycle transitions or approvals.

Neo4j is implemented strictly as a derived read model. Object Store/Event Store remain regulatory authority.

## Deterministic synchronization contract

`GraphSyncService` wraps the canonical traceability projection in `GraphSyncBatch`.

The batch contract includes:

- schema `graph-sync-batch-1.0`
- exact root/version/depth
- `source_authority = "object_store"`
- `approval_authority = "object_store"`
- `read_only = true`
- `sync_mode = "replace_exact_scope"`
- canonical JSON
- SHA-256 over the canonical synchronization payload

`GraphSyncAdapter` is infrastructure-neutral.

`GraphSyncService.sync_scope()` rejects an adapter acknowledgement unless checksum, root, depth, node count and edge count exactly match the submitted batch.

This prevents an infrastructure adapter from reporting success for a different, partial or stale graph scope.

## Neo4j materialization adapter

The optional `Neo4jGraphSyncAdapter` implements the synchronization contract without making Neo4j a core runtime dependency.

Optional dependency:

`orkp[graph]` → `neo4j>=6.0,<7.0`

Materialization schema:

- `:ORKPObjectVersion`, unique `(object_uuid, object_version)`
- `:ORKPSyncScope`, unique `scope_key`
- `:ORKP_RELATION`, unique `relation_uuid`

Regulatory object/relation types remain properties rather than dynamically interpolated Neo4j labels or relationship types.

`replace_exact_scope` behavior:

- runs in one explicit `Session.execute_write()` transaction
- removes only the replaced scope's previous membership
- upserts exact canonical nodes and edges
- preserves entities shared by other synchronized scopes
- deletes only entities whose scope membership becomes empty
- uses `DELETE`, not `DETACH DELETE`, for unused nodes so unexpected shared-edge invariants fail rather than silently deleting graph data

Arbitrary relation metadata is persisted as deterministic canonical JSON rather than expanded into uncontrolled Neo4j properties.

Driver/schema/transaction failures become typed `GraphSynchronizationError`.

## Completed issues

- #27 — canonical versioned traceability projection
- #28 — exact-version change impact analysis
- #29 — deterministic graph synchronization contract
- #30 — Neo4j exact-scope materialization adapter

## Representative implementation / hardening commits

- `f28a10c`, `d947557`, `48a9b9b` — strict traceability graph models/service/API
- `527f119`, `fdcde03` — traceability regressions
- `8ccd103`, `07b26fb`, `8e133d1` — exact-version impact model/service/API
- `b3e75c3`, `e13dd25` — impact payload integrity and tamper regressions
- `8b0a667`, `5352167`, `d1530da` — deterministic sync models/service and tests
- `78d7b48`, `921f15a`, `2f67ae8` — optional Neo4j dependency, adapter and unit regressions
- `0c72429` — final Ruff-only formatting of Neo4j adapter tests

## Audit / reproducibility properties

Epic 008 preserves these invariants:

- exact UUID/version identity
- active-relation-only projection
- deterministic traversal and output ordering
- deterministic shortest impact paths
- canonical JSON + SHA-256 synchronization payload
- explicit adapter acknowledgement validation
- no graph-owned approval authority
- no graph mutation of Object Store regulatory state
- no dynamic Cypher identifiers derived from regulatory data
- atomic exact-scope Neo4j replacement
- shared-scope membership protection

## Open non-blocking verification item

Issue #31 — **Live Neo4j Exact-Scope Integration Verification** remains open.

It is an opt-in operational/infrastructure verification and is not an unmet `GRAPH-CORE` requirement. The test is skipped unless `ORKP_NEO4J_URI`, `ORKP_NEO4J_USERNAME` and `ORKP_NEO4J_PASSWORD` are configured.

The live test is intended to prove against a real Neo4j engine that:

- the exact constraint syntax is accepted
- v1/v2 scopes materialize independently
- shared nodes keep multiple scope memberships
- replacing one scope removes only that scope's stale relation state

Until that live environment is configured, the adapter remains covered by fake-driver unit regressions and the normal suite remains green with one intentional skip.

## Known non-blocking item

The suite emits one Starlette/httpx deprecation warning from `fastapi.testclient`. It does not affect graph traceability, impact, synchronization or regulatory-authority semantics.

## Completion decision

Epic 008 is accepted as functionally complete for `TASK-GRAPH-0001` based on the verified **528 passed / 1 skipped** normal-development gate, strict lint/spec/backlog checks and the completed exact-version traceability, impact, synchronization and Neo4j materialization contracts.

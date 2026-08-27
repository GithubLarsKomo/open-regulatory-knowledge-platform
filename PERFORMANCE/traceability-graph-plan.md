# Performance Optimization Plan: Traceability Graph

## Problem

The merged E2E performance baseline identifies exact-version traceability traversal as the largest remaining deterministic database-roundtrip hotspot.

Representative workload:

- one root exact object version;
- 50 directly connected exact-version nodes;
- traversal depth 1;
- 51 projected nodes;
- **106 SQL statements**.

Timing is observational. SQL statement count is the deterministic gate.

## Root cause

`GraphProjectionService.traceability()` currently performs object materialization node-by-node:

1. the root is loaded once before traversal with an object query plus a version query;
2. the root is loaded a second time when dequeued, again with two queries;
3. active outgoing relations are loaded in one query;
4. active incoming relations are loaded in a second query;
5. each of the 50 adjacent nodes is later loaded with its own object query plus version query.

For the measured depth-1 star this is therefore exactly:

- root pre-validation: 2 statements;
- root traversal reload: 2 statements;
- root relations: 2 statements;
- 50 adjacent node loads: 100 statements;
- total: **106 statements**.

The dominant mechanism is deterministic N+1 exact-version materialization, not CPU time or a missing index.

## Selected optimization

Replace node-oriented traversal reads with breadth/frontier-oriented set reads while preserving exact-version graph semantics.

1. Validate and materialize the root exact version with one joined object/version query.
2. Maintain the BFS frontier as exact `(object_uuid, version_no)` pairs.
3. For each traversed level, load all active relations touching the complete frontier in one query using exact source/target version pairs.
4. Discover adjacent exact-version pairs in memory and deduplicate edges/nodes by their existing identities.
5. After traversal, load all discovered non-root object/version contexts in one set query.
6. Project nodes and edges with the existing deterministic sorting and read-only model semantics.

The query shape therefore scales with traversal **depth**, not node count.

## Performance hypothesis

For valid graphs:

- depth 0: **1 SQL statement**;
- depth 1: **<=3 SQL statements**;
- depth 2: **<=4 SQL statements**;
- general depth `d > 0`: approximately **d + 2 statements**, independent of frontier width.

For the representative 51-node depth-1 E2E scenario:

- before: **106 statements**;
- target: **<=3 statements**;
- expected reduction: at least **97.1%**.

## Functional invariants

- Public `GraphProjectionService.traceability()` signature and return model unchanged.
- UUID parsing and depth validation unchanged.
- Root object-not-found and version-not-found errors remain typed.
- Graph identity remains `(object_uuid, object_version)`, not object UUID alone.
- Incoming and outgoing active relations remain projected.
- Inactive relations remain excluded.
- Relation source and target versions are respected exactly.
- Historical versions remain distinct from current versions.
- Soft-deleted objects remain projectable because the existing graph uses `get_by_uuid_including_deleted()` semantics.
- Depth behavior remains breadth-first and bounded to 0..10.
- Nodes and edges remain duplicate-free and deterministically sorted.
- Projection remains read-only and Object Store authoritative.
- `impact_analysis()` semantics remain unchanged because it consumes `traceability()` output.

## Regression gates

### Functional

- Existing graph projection tests pass unchanged.
- Existing impact-analysis tests pass unchanged.
- Version-distinct traversal remains correct.
- Incoming/outgoing traversal remains correct.
- Inactive relation exclusion remains correct.
- Depth-2 traversal remains correct.
- Full pytest suite passes on Python 3.10 and 3.12.

### Performance

- 51-node depth-1 star: **<=3 SQL statements**.
- A 51-node two-level graph at depth 2: **<=4 SQL statements**.
- Statement count must not grow with frontier width at a fixed depth.
- Baseline freeze remains 6 statements.
- Hybrid keyword retrieval remains 41 statements.
- PER DOCX render remains 10 statements.
- Existing read/write performance gates remain unchanged.

## Architecture boundary

Set-oriented graph reads are persistence concerns. They will live in a small DB-layer graph read repository using the same SQLAlchemy `Session` as the existing `RegulatoryObjectRepository`. Domain traversal remains responsible only for BFS semantics and projection.

This avoids putting SQLAlchemy query construction into the domain service while also avoiding unrelated changes to the general object repository.

## Rejected alternatives

### Cache projected graph nodes

Rejected. The N+1 roundtrips can be removed directly without cache invalidation or stale-data semantics.

### Precompute/materialize the graph

Rejected. No evidence justifies a second source of truth; the Object Store remains authoritative.

### Add indexes first

Rejected. Query count, not individual query execution cost, is the measured dominant defect.

### Parallelize per-node reads

Rejected. Parallel N+1 remains N+1 and adds connection/concurrency complexity.

### Special-case only depth 1

Rejected. The optimization must improve the general bounded BFS path and preserve depth-2+ behavior.

## Rollback

The change is confined to graph read persistence, traversal materialization, focused deterministic tests and performance documentation. Revert if graph semantics change, runtime/provider compatibility fails, or the depth-based query budgets are not met.

## Stop rule

Stop when the 51-node depth-1 path is <=3 statements, depth-2 remains <=4 statements, all semantic tests pass on both supported Python runtimes, unaffected performance budgets remain stable, and the simplification review finds no unnecessary cache, schema or infrastructure layer.
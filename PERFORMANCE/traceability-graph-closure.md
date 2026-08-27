# Optimization Closure: Traceability Graph Roundtrips

## Scope

This closure covers exact-version traceability projection in `GraphProjectionService.traceability()` and the persistence reads required for bounded breadth-first graph traversal. Object Store writes, relation lifecycle, graph synchronization, report generation and retrieval are unchanged.

## Baseline vs optimized state

| Metric | Before | After | Change |
|---|---:|---:|---:|
| SQL statements, 51 nodes / depth 1 | 106 | 3 | -103 / -97.2% |
| Depth 0 root-only projection | 2+ before node traversal | 1 | one joined root read |
| Depth 2 representative 51-node graph | node-scaled | <=4 | depth-scaled guard |
| Baseline freeze, 100 items | 6 | 6 | unchanged |
| Hybrid keyword retrieval, 1,000 objects | 41 | 41 | unchanged |
| PER DOCX render | 10 | 10 | unchanged |
| repository read baselines | 1 each | 1 each | unchanged |
| `create_object` | 3 | 3 | unchanged |
| `create_relation` | 2 | 2 | unchanged |

SQL statement count is the deterministic result. Hosted-runner timing remains observational and non-gating. On the first complete optimized Python 3.12 run, the depth-1 51-node graph had a median of 4.591 ms with all five samples executing exactly three statements.

## Mechanism confirmed

The original traversal performed database reads per graph node:

1. load the root object and requested version separately;
2. load the same root again when traversal dequeued it;
3. fetch outgoing and incoming relations separately;
4. load each adjacent object and exact version separately.

For a root plus 50 adjacent nodes, this produced exactly 106 statements.

The optimized path is frontier-oriented:

1. load and validate the root object plus requested exact version in one joined query;
2. represent the BFS frontier as exact `(object_uuid, version_no)` pairs;
3. load all active relations touching the complete frontier in one set query per traversed level;
4. discover adjacent exact-version identities in memory while deduplicating by the existing node and relation keys;
5. load all discovered non-root object/version contexts in one set query;
6. project and sort nodes/edges with the existing deterministic model semantics.

The representative depth-1 path therefore uses one root query, one frontier-relation query and one non-root context query: **three SQL statements regardless of frontier width**.

## Functional evidence

The first complete optimized Python 3.12 CI path passed all substantive gates:

- Ruff lint and formatting;
- **563 tests passed, 1 skipped**;
- existing graph projection tests;
- existing impact-analysis tests;
- new deterministic depth-0/1/2 query-budget tests;
- read performance baseline;
- write performance baseline;
- end-to-end performance baseline;
- specification linter;
- backlog generator;
- performance artifact generation.

That run failed only the generated-file synchronization gate because the new performance documentation increased the linter's scanned-file count. The final generated report is synchronized after this closure document and the complete CI matrix must pass on both supported Python runtimes before merge.

## Preserved invariants

- Public `traceability()` signature and `TraceabilityGraph` model are unchanged.
- UUID and depth validation behavior is unchanged.
- Root object absence remains `ObjectNotFoundError`.
- Missing requested root version remains `ObjectVersionNotFoundError`.
- Graph node identity remains the exact `(object_uuid, object_version)` pair.
- Historical versions remain distinguishable from current versions.
- Incoming and outgoing active relations remain traversable.
- Inactive relations remain excluded.
- Relation endpoint versions are matched exactly.
- Soft-deleted objects remain projectable because no lifecycle-state filter is introduced for node materialization.
- Breadth-first depth boundaries remain 0..10.
- Node and edge output remains duplicate-free and deterministically sorted.
- Projection remains read-only and Object Store authoritative.
- `impact_analysis()` continues to consume the same traceability model and preserves its path semantics.

## Architecture and simplification pass

One small production abstraction was added: `GraphReadRepository`. It is intentionally limited to three stateless set-oriented read operations over the same SQLAlchemy `Session` used by the Object Store repository.

Keeping these queries in the DB layer avoids two worse alternatives:

- leaking SQLAlchemy query construction into the domain traversal service;
- expanding the general `RegulatoryObjectRepository` with graph-specific frontier operations unrelated to its existing object/relation CRUD surface.

No additional service, cache or compatibility layer was introduced.

Deliberately not introduced:

- cache or invalidation logic;
- materialized/precomputed graph state;
- async or parallel database reads;
- schema changes;
- new indexes;
- background jobs;
- provider-specific stored procedures;
- temporary production instrumentation.

The domain service is simpler in the key performance dimension: it now expresses BFS in terms of frontier sets rather than performing persistence calls inside the per-node loop.

## Regression guards

`tests/test_graph_performance.py` provides deterministic scaling guards:

- depth 0 root-only projection must execute exactly **1 statement**;
- a 51-node depth-1 star must execute **<=3 statements**;
- a 51-node depth-2 graph must execute **<=4 statements**.

These guards detect a return of node-count-dependent N+1 behavior while avoiding unstable wall-clock assertions.

Existing graph tests continue to cover incoming/outgoing relations, exact-version identity, inactive relation exclusion, deterministic ordering, read-only behavior, depth traversal and typed failures.

## Residual performance opportunities

After this change the measured E2E deterministic statement ranking is:

1. hybrid keyword retrieval, 1,000 objects / 20 hits: **41 statements**;
2. PER DOCX render: **10 statements**;
3. baseline freeze, 100 items: **6 statements**;
4. traceability graph, 51 nodes / depth 1: **3 statements**.

Traceability is therefore no longer a material roundtrip hotspot in the measured E2E set.

## Stop decision

The selected target is met exactly: **106 -> 3 SQL statements**, a 97.2% reduction, while all substantive functional tests and unaffected deterministic performance budgets remain stable. Further graph-specific roundtrip optimization would have substantially lower marginal value and does not belong in this slice.
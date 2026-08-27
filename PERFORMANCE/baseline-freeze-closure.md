# Optimization Closure: Baseline Freeze Roundtrips

## Scope

This closure covers only `RegulatoryObjectRepository.create_baseline()` and the persistence work required to freeze an exact set of object versions. Higher-level report construction, retrieval, graph traversal, schema design and indexing are unchanged.

## Baseline vs optimized state

| Metric | Before | After | Change |
|---|---:|---:|---:|
| SQL statements, `baseline_create_100` | 304 | 6 | -298 / -98.0% |
| Python 3.12 median, hosted SQLite runner | 62.691 ms | 5.383 ms | ~-91.4% observed |
| Hybrid keyword retrieval, 1,000 objects | 41 | 41 | unchanged |
| Traceability graph, 51 nodes | 106 | 106 | unchanged |
| PER DOCX render | 10 | 10 | unchanged |
| repository read baselines | 1 each | 1 each | unchanged |
| `create_object` | 3 | 3 | unchanged |
| `create_relation` | 2 | 2 | unchanged |

SQL statement count is the deterministic result. Hosted-runner timing is observational and non-gating; timing comparisons are useful only as supporting evidence because runner placement and load vary.

## Mechanism confirmed

Before the change, each frozen `(object_uuid, version_no)` pair triggered two reads: one for the exact `ObjectVersion` and one for its `RegulatoryObject` metadata. The resulting `BaselineItem` rows were then flushed through the ORM individually.

The optimized path keeps the same public repository operation but performs the persistence work set-wise:

1. insert and flush the new `Baseline` identity;
2. load all distinct requested exact version/object contexts with one composite set query;
3. validate every original requested pair against that context;
4. build the same snapshot rows from exact `ObjectVersion.payload_json` values;
5. persist all baseline-item rows with one bulk insert execution;
6. emit the same `baseline_frozen` event;
7. commit under the same caller-owned transaction and verify the resulting item set.

For the 100-item E2E workload the full create + commit + verification path is consistently **6 SQL driver executions**, so statement count no longer scales linearly with item count.

## Functional evidence

The first complete optimized Python 3.12 CI run passed all substantive gates:

- Ruff lint and formatting;
- **560 tests passed, 1 skipped**;
- read performance baseline;
- write performance baseline;
- end-to-end performance baseline;
- specification linter;
- backlog generator;
- performance artifact generation.

That run failed only the generated-file synchronization gate because adding the performance plan and task increased the specification linter's scanned-file count. This closure adds one final documentation file, so the generated report is synchronized once after closure and the final CI matrix must pass on both supported runtimes.

## Preserved invariants

- Public `create_baseline()` signature and return type unchanged.
- Caller-selected exact versions are frozen; current versions are not substituted.
- `snapshot_json` remains the exact selected version payload.
- Stored `object_type` remains derived from the referenced object.
- Soft-deleted objects remain eligible, matching the previous `get_by_uuid_including_deleted()` behavior.
- Missing exact versions still raise `BaselineValidationError` with the existing message shape.
- Original input pairs remain the source of persisted baseline items; lookup deduplication does not silently change requested persistence semantics.
- Empty baselines remain supported.
- One `baseline_frozen` event is emitted with the same name and original item count.
- Commit/rollback ownership remains with the caller.
- Existing uniqueness and foreign-key constraints remain authoritative.

## Simplification pass

No new production abstraction was required. The change remains inside the repository persistence method because both the composite exact-version lookup and bulk snapshot insert are persistence concerns.

Deliberately not introduced:

- cache or invalidation logic;
- async or parallel database access;
- schema changes;
- additional indexes;
- background jobs;
- provider-specific stored procedures;
- higher-level service workarounds;
- temporary production instrumentation.

The implementation uses existing SQLAlchemy set primitives rather than adding a second baseline service or compatibility layer.

## Regression guards

`tests/test_baseline_performance.py` provides deterministic and semantic guards:

- a 100-item create + commit + verification flow must stay at **<=6 SQL statements**;
- all 100 exact snapshots are present with the expected version and object type;
- a soft-deleted object's exact historical payload remains baseline-compatible;
- the `baseline_frozen` event preserves the original requested item count.

Existing repository tests continue to cover immutable historical snapshots and missing-version validation.

## Residual performance opportunities

With baseline creation reduced to six statements, it is no longer a material database-roundtrip hotspot in the measured E2E set. The current deterministic ranking is now:

1. traceability graph, 51 nodes: **106 statements**;
2. hybrid keyword retrieval, 1,000 objects / 20 hits: **41 statements**;
3. PER DOCX render: **10 statements**;
4. baseline freeze, 100 items: **6 statements**.

The graph path is therefore the next independent optimization candidate.

## Stop decision

The selected target is met exactly at the hard gate: **304 -> 6 SQL statements**, a 98.0% reduction, while functional tests and all unaffected performance budgets remain stable. Further baseline-specific optimization would have substantially lower marginal value and does not belong in this slice.

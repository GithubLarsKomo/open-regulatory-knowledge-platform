# Optimization Closure: Relation Validation Roundtrips

## Scope

This closure covers only `RegulatoryObjectRepository.create_relation()` endpoint validation. No broader repository, API or database optimization is implied.

## Baseline vs. optimized state

| Metric | Before | After | Change |
|---|---:|---:|---:|
| SQL statements per valid relation incl. `flush()` | 5 | 2 | -60% |
| Python 3.12 median, hosted SQLite runner | 1.359 ms | 0.859 ms | ~-36.8% observed |
| `create_object` SQL statements | 3 | 3 | unchanged |
| measured read/list SQL statements | 1 | 1 | unchanged |

The SQL-statement reduction is the deterministic performance result for this slice. Hosted-runner timing remains observational and is not a hard acceptance threshold.

## Functional evidence

The optimized implementation has passed the full ORKP pytest suite on Python 3.10 and Python 3.12 in CI, including the existing relation validation cases and the new deterministic statement-budget regression test.

The verification run reported:

- 555 passed;
- 1 skipped;
- relation creation statement budget test passed;
- read performance baseline passed;
- write performance baseline passed.

A final clean matrix rerun is required only to clear the generated-artifact consistency gate after adding this closure document.

## Preserved invariants

- Public `create_relation()` signature unchanged.
- Source-version error precedence unchanged.
- Target-version error behavior unchanged.
- Canonical relation-type validation unchanged.
- Central `validate_relation()` policy remains authoritative.
- Deleted objects remain available for endpoint type resolution because the joined query does not filter lifecycle state.
- Repository method still adds a pending relation without committing.
- Same-object/same-version relation endpoints are handled by the keyed endpoint context and covered by a regression test.

## Simplification pass

No additional abstraction was introduced after the successful optimization.

Specifically:

- no cache or invalidation layer;
- no async/parallel database access;
- no schema or index change;
- no new service/helper solely for one call site;
- no compatibility branch or temporary production instrumentation;
- existing general-purpose `get_version()` and `get_by_uuid_including_deleted()` helpers remain because they are used elsewhere and are not obsolete.

The final implementation keeps the optimization local to the method that owns the combined validation context. Extracting the query into another helper would add indirection without a second consumer, so it is intentionally not done.

## Regression guard

`tests/test_repository_relation_performance.py` enforces that a successful relation creation, including `flush()`, executes at most two SQL statements.

The CI baseline harness continues to record:

- all read/list statement counts;
- `create_object` statement count;
- `create_relation` statement count;
- non-gating timing distributions.

This catches both local roundtrip regressions and accidental changes to unrelated measured paths.

## Residual uncertainty

The deterministic statement-count improvement is database-independent at the application level, but the benchmark environment uses SQLite. This evidence does not claim a specific MariaDB latency percentage, query-plan improvement or production contention benefit.

A MariaDB integration benchmark is warranted only if a future requirement needs production-database latency, optimizer-plan or concurrency evidence. It is not required to justify the current four-read-to-one-read reduction.

## Stop decision

The target is met: valid relation creation is reduced from five to two SQL statements without functional regression or added infrastructure complexity. No further optimization is justified in this slice.

# Performance Plan: Baseline Post-Commit Refresh

## Problem and measured baseline

`baseline_create_100` is currently the largest remaining measured end-to-end SQL roundtrip path at **6 statements**.

The repository freeze implementation itself is already set-based and constant-cost after the earlier 304 -> 6 optimization. Static decomposition of the current measured operation shows:

1. insert `Baseline`;
2. select all exact requested `ObjectVersion` + `RegulatoryObject` context in one set query;
3. bulk insert all `BaselineItem` snapshots;
4. insert `baseline_frozen` event;
5. after `commit()`, SQLAlchemy refreshes the expired `Baseline` ORM row only because the caller accesses `baseline.baseline_uuid` again;
6. select `BaselineItem` rows for the deliberate post-create verification.

The fifth step is avoidable. The sixth is part of the benchmark contract and remains intentionally present.

## Root cause

SQLAlchemy expires ORM state on commit by default. The generated baseline UUID is already final immediately after the repository flush, but callers keep the ORM object and dereference it only after commit. This turns a locally available immutable identity into a redundant database roundtrip.

This is an ORM lifecycle / unnecessary-work issue, not a schema, index, algorithm or bulk-persistence problem.

## Selected optimization

Capture the generated `baseline_uuid` before `commit()` and use that immutable value for the post-create verification.

Apply the same discipline to production baseline response construction where practical: response values that are already final before commit should be materialized before commit rather than rehydrating the just-created ORM entity afterwards.

## Rejected alternatives

- **Remove item verification:** rejected because it would change the E2E benchmark contract instead of optimizing the measured workflow.
- **Set `expire_on_commit=False` globally:** rejected because that changes session-wide consistency semantics to save one read in a narrow path.
- **Schema/index changes:** no evidence they help; the remaining create work is already one set read plus bulk writes.
- **Cache:** unnecessary and would add invalidation complexity.
- **Async/parallel writes:** no evidence and inappropriate for this atomic transaction.
- **Eliminate the set validation query:** rejected because exact-version existence and snapshot provenance are functional invariants.

## Performance budget

Hard deterministic gate:

- `baseline_create_100`: **exactly 5 SQL statements** for create + commit + item verification.

Unchanged budgets:

- `per_render_docx`: 5
- `graph_traceability_depth1_51`: 3
- `hybrid_keyword_1000`: 2
- repository read scenarios: 1
- `create_object`: 3
- `create_relation`: 2

Timing remains observational/non-gating because hosted-runner variance is material.

## Functional invariants

- exact requested object versions are frozen;
- exact `snapshot_json` payloads are preserved;
- stored object types are unchanged;
- soft-deleted exact historical versions remain eligible;
- missing versions still fail with `BaselineValidationError`;
- one `baseline_frozen` event is emitted with the original requested item count;
- caller-owned commit/rollback semantics remain unchanged;
- the 100-item verification still reads and validates all 100 persisted items.

## Implementation slices

1. Capture the baseline UUID before commit in the deterministic baseline performance test and E2E harness.
2. Tighten the query guard from `<= 6` to exact `5`.
3. Keep all semantic assertions unchanged.
4. Run the full Python 3.10/3.12 matrix and all read/write/E2E performance harnesses.
5. Run simplification pass and add closure documentation.

## Rollback

Revert the pre-commit identity capture and restore the prior six-statement guard. No migration, schema or persisted-data rollback is required.

## Definition of done

- 100-item baseline create + commit + verification is consistently 5 statements on Python 3.10 and 3.12;
- all functional tests pass;
- all unrelated performance budgets remain unchanged;
- spec/backlog/generated-file gates pass;
- no broader session or architecture change is introduced.

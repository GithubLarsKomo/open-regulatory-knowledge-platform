# TASK: Remove Baseline Post-Commit Refresh

## Objective

Reduce `baseline_create_100` from 6 SQL statements to 5 without changing frozen-baseline semantics or the deliberate post-create item verification.

## Baseline

- current E2E budget: 6 statements
- core freeze persistence is already constant-cost and set-based
- one redundant statement is an ORM refresh caused by reading `baseline.baseline_uuid` after commit
- item verification remains in scope and must not be removed to make the metric look better

## Tasks

- [x] Decompose the six statements and identify the redundant post-commit refresh.
- [ ] Capture generated baseline UUID before commit in the E2E harness.
- [ ] Tighten the deterministic 100-item regression guard to exactly 5 statements.
- [ ] Preserve all semantic verification of the 100 frozen items.
- [ ] Run full Python 3.10 and 3.12 CI.
- [ ] Confirm `baseline_create_100` is exactly 5 on both runtimes.
- [ ] Confirm PER render, graph, hybrid, read and write budgets are unchanged.
- [ ] Run simplification pass and document closure.
- [ ] Merge only after the final head is fully green.

## Functional gate

- 100 exact version snapshots persist and are readable after commit
- object type and version are unchanged
- historical soft-deleted object snapshots remain supported
- missing exact versions still fail
- one `baseline_frozen` event retains the original requested item count
- caller-owned commit/rollback semantics remain unchanged

## Performance gate

- `baseline_create_100`: exactly 5 statements
- `per_render_docx`: unchanged at 5
- `graph_traceability_depth1_51`: unchanged at 3
- `hybrid_keyword_1000`: unchanged at 2
- repository reads: unchanged at 1
- `create_object`: unchanged at 3
- `create_relation`: unchanged at 2

## Compatibility

- Python 3.10 and 3.12
- SQLAlchemy 2.x
- SQLite CI semantics
- no schema migration
- default `expire_on_commit` semantics remain unchanged

## Out of scope

- removing post-create item verification
- changing session factory expiration semantics
- eliminating exact-version validation
- schema/index changes
- caching
- async/parallel baseline persistence
- timing-based CI gates

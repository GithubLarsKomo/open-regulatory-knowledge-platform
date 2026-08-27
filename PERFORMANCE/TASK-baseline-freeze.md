# TASK: Optimize Baseline Freeze Roundtrips

## Objective

Reduce the deterministic E2E `baseline_create_100` workload from **304 SQL statements to <=6** without changing frozen-version semantics, snapshot content, deleted-object handling, event creation or caller-controlled transaction behavior.

## Baseline

- Workload: 100 exact `(object_uuid, version_no)` references.
- Result size: 100 baseline items.
- Current E2E budget: **304 SQL statements**.
- Measurement: `tools/performance_e2e_baseline.py`.

## Root cause

`RegulatoryObjectRepository.create_baseline()` performs one version query and one object query per input item and then flushes baseline items individually.

## Implementation

- [ ] Replace per-item version/object reads with one set-oriented exact-version/object-context query.
- [ ] Preserve the original requested pair list for validation and persisted snapshots.
- [ ] Preserve support for deleted objects.
- [ ] Preserve missing-version `BaselineValidationError` behavior.
- [ ] Bulk-persist baseline item snapshots when non-empty.
- [ ] Preserve exact snapshot JSON and object type.
- [ ] Preserve the existing `baseline_frozen` event payload.
- [ ] Preserve empty-baseline behavior.
- [ ] Do not add cache, schema changes, indexes, async logic or infrastructure.

## Functional gate

- [ ] Existing baseline repository tests pass unchanged.
- [ ] Exact old-version snapshots remain immutable after later updates.
- [ ] Missing versions still fail with `BaselineValidationError`.
- [ ] Deleted objects remain baseline-compatible with correct type/payload.
- [ ] Event item count equals the original request length.
- [ ] Full pytest suite passes on Python 3.10 and 3.12.

## Performance gate

- [ ] `baseline_create_100` executes <=6 SQL statements.
- [ ] No SQL count grows linearly with baseline item count.
- [ ] `hybrid_keyword_1000` remains 41 statements.
- [ ] Graph traceability remains 106 statements.
- [ ] PER DOCX render remains 10 statements.
- [ ] Existing read/write performance baselines remain unchanged.

## Verification

```bash
python -m pytest -q
python tools/performance_baseline.py
python tools/performance_write_baseline.py
python tools/performance_e2e_baseline.py
```

## Definition of Done

The baseline freeze uses set-oriented validation and persistence, deterministic query scaling is constant for the representative workload, semantic behavior is unchanged, CI is green on both supported Python runtimes, and the simplification pass confirms that no unnecessary abstraction or infrastructure was introduced.

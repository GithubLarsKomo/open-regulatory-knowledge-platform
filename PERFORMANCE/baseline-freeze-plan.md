# Performance Optimization Plan: Baseline Freeze

## Problem

The merged E2E performance baseline identifies baseline creation as the next independent database-roundtrip hotspot after hybrid retrieval.

Representative workload:

- 100 exact object-version references;
- one frozen baseline;
- result verification through `list_baseline_items()`;
- **304 SQL statements** in the current E2E harness.

Hosted-runner timing is observational. SQL statement count is the deterministic gate.

## Root cause

`RegulatoryObjectRepository.create_baseline()` currently loops over every requested object-version pair and performs:

1. `get_version(object_uuid, version_no)`;
2. `get_by_uuid_including_deleted(object_uuid)`;
3. construction of one `BaselineItem` ORM row.

For 100 items, the validation/snapshot context alone therefore causes **200 avoidable SELECT roundtrips**. The subsequent baseline-item flush also emits one insert operation per item on the measured SQLite path.

## Selected optimization

Perform the freeze in set-oriented persistence operations while preserving the public repository API and baseline semantics:

1. create and flush the `Baseline` row exactly as today;
2. load all requested exact versions together with their object metadata in one set query;
3. validate every original requested pair against that context;
4. construct snapshot rows in the original input order;
5. persist all snapshot rows with one executemany/bulk insert when the list is non-empty;
6. emit the same `baseline_frozen` event;
7. leave transaction commit/rollback ownership with the caller exactly as today.

## Performance hypothesis

For the 100-item E2E scenario:

- Before: **304 SQL statements**.
- Expected optimized path: approximately **5 SQL driver executions** including the final verification read.
- Deterministic gate: **<=6 statements** to allow provider-level execution differences while still detecting any return of per-item roundtrips.

Expected mechanism:

- 1 baseline insert/flush;
- 1 set query for exact version + object context;
- 1 bulk baseline-item insert;
- 1 event insert during commit;
- 1 verification query.

## Functional invariants

- Same `RegulatoryObjectRepository.create_baseline()` signature and return type.
- Same exact requested version is frozen; current version is irrelevant.
- Same `snapshot_json` payload as the selected `ObjectVersion`.
- Same object type stored in each baseline item.
- Deleted objects remain eligible because the existing path uses `get_by_uuid_including_deleted()`.
- Missing object-version pairs raise `BaselineValidationError` with the same message shape.
- Input duplicates are not silently deduplicated from the persisted request semantics.
- Empty baselines remain supported.
- One `baseline_frozen` event is emitted with the same name/item-count data.
- Caller-controlled transaction semantics remain unchanged.
- No schema, index, cache, queue or infrastructure change.

## Regression gates

### Functional

- Existing repository baseline tests pass unchanged.
- Snapshot immutability remains correct after a newer version is created.
- Missing version still raises `BaselineValidationError`.
- Deleted-object baseline preserves object type and exact payload.
- Event history contains one `baseline_frozen` event with the correct item count.
- Full pytest suite passes on Python 3.10 and 3.12.

### Performance

- 100-item create + commit + verification: **<=6 SQL statements**.
- `hybrid_keyword_1000` remains 41 statements.
- Graph traceability remains 106 statements unless independently optimized.
- PER DOCX render remains 10 statements.
- Existing read/write baseline gates remain unchanged.

## Rejected alternatives

### Skip version validation

Rejected. Reproducible baselines require every frozen reference to be proven to exist before the baseline is accepted.

### Freeze only current versions

Rejected. Baselines intentionally freeze caller-selected exact versions and must remain reproducible after later object updates.

### Cache object/version metadata

Rejected. The roundtrips can be removed directly with a set query without introducing invalidation complexity.

### Add schema or indexes

Rejected. The measured problem is N+1/set-processing behavior, not an evidenced missing-index problem.

### Change higher-level report services

Rejected. The hotspot is in the shared repository primitive and should be corrected once at the persistence boundary.

## Rollback

The change is confined to baseline persistence and focused regression tests. Revert if baseline semantics change, provider compatibility fails, or the <=6-statement gate is not met.

## Stop rule

Stop when the 100-item E2E freeze is <=6 SQL statements, all functional invariants pass on both supported runtimes, other E2E budgets remain unchanged, and the simplification review finds no unnecessary production abstraction.

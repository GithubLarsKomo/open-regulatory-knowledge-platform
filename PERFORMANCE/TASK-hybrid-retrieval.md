# TASK: Eliminate Keyword Retrieval N+1 Scan

## Objective

Reduce `hybrid_keyword_1000` from **1,041 SQL statements to <=41** without changing keyword retrieval semantics, ranking, exact-version grounding, vector retrieval, graph retrieval or hit validation.

## Baseline

- Workload: 1,000 current Object Store objects, 100 keyword matches, `keyword_limit=20`.
- Result size: 20.
- Python 3.10: 1,041 SQL statements; median 222.794 ms.
- Measurement: `tools/performance_e2e_baseline.py`.

## Root cause

`ObjectStoreKeywordRetrievalAdapter.search()` executes one `get_version()` query for every object returned by `list_objects()`.

## Implementation

- [ ] Add a DB-layer query for non-deleted objects joined to their `current_version`.
- [ ] Preserve `updated_at DESC` scan order and `scan_limit`.
- [ ] Change keyword retrieval to consume the joined object/version rows.
- [ ] Preserve `ai_draft` exclusion.
- [ ] Preserve tokenization, phrase bonus, score calculation and deterministic sorting.
- [ ] Preserve exact-version hit references.
- [ ] Do not change `HybridRetrievalService._validate_hit()` in this slice.
- [ ] Do not add caching, full-text infrastructure, schema changes or new indexes.

## Functional gate

- [ ] Existing hybrid retrieval tests pass unchanged.
- [ ] Existing hybrid retrieval security tests pass unchanged.
- [ ] Current-version test still returns the newest exact version.
- [ ] Deleted objects remain excluded.
- [ ] Retrieval remains read-only.
- [ ] Full pytest suite passes on Python 3.10 and 3.12.

## Performance gate

- [ ] Joined keyword scan executes exactly 1 SQL statement.
- [ ] `hybrid_keyword_1000` executes <=41 SQL statements.
- [ ] Baseline freeze remains 304 statements.
- [ ] Graph traceability remains 106 statements.
- [ ] PER DOCX render remains 10 statements.
- [ ] Existing repository read/write baselines remain unchanged.

## Verification

```bash
python -m pytest -q
python tools/performance_baseline.py
python tools/performance_write_baseline.py
python tools/performance_e2e_baseline.py
```

## Definition of Done

The N+1 current-version scan is removed, semantic behavior is unchanged, the deterministic query budget is met on both supported Python runtimes, CI is fully green, Before/After evidence is documented, and the simplification pass finds no unnecessary production complexity.
# Hybrid keyword prefilter performance plan

## Baseline

Measured on `master` commit `0779c2c84744cf2fbaf8881f2143ecef52f64ca0` in the existing CI E2E harness:

- `hybrid_keyword_1000`: 2 SQL statements, ~28.2 ms median on Python 3.12
- `baseline_create_100`: 5 SQL statements, ~6.7 ms median
- `graph_traceability_depth1_51`: 3 SQL statements, ~4.8 ms median
- `per_render_docx`: 5 SQL statements, ~2.5 ms median

Timing remains observational; query counts are deterministic.

## Root cause

`ObjectStoreKeywordRetrievalAdapter.search()` currently loads up to 5,000 complete current object/version ORM pairs and then, for every row, serializes the JSON payload, tokenizes it and discards non-matches in Python. The 1,000-object benchmark therefore processes all 1,000 payloads although only a small subset can match.

## Optimization

Add a read-only database prefilter that:

1. preserves the existing newest-`scan_limit` candidate window,
2. excludes deleted objects and `ai_draft` as before,
3. uses the query tokens only as a safe SQL superset filter on serialized JSON,
4. returns minimal keyword-candidate fields rather than full ORM entities,
5. keeps the existing Python canonical tokenization, scoring, sorting and final limit unchanged.

The SQL prefilter is not authoritative scoring. Every returned candidate still passes the existing `_searchable_text()` and exact scoring logic, so false-positive SQL matches cannot alter ranking semantics.

## Gates

- Query count remains exactly 2 for `hybrid_keyword_1000`.
- Existing keyword/hybrid retrieval behavior remains unchanged.
- New tests prove that the `scan_limit` window is preserved and that SQL-prefilter false positives are removed by existing Python scoring.
- Compare E2E median timing on equivalent CI runtime; timing is evidence, not a hard gate.
- No schema, index, cache, FTS, external search engine or API contract change.

## Stop rule

Close this slice if candidate materialization is reduced without semantic regression. Do not introduce FTS/index/schema work unless a later production-like database benchmark justifies it.
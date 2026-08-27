# Optimization Closure: Hybrid Keyword Retrieval N+1 Scan

## Scope

This closure covers only the current-version scan inside `ObjectStoreKeywordRetrievalAdapter.search()`. Exact hit validation, vector retrieval, graph retrieval, keyword semantics and ranking remain separate concerns and are unchanged.

## Baseline vs optimized state

| Metric | Before | After | Change |
|---|---:|---:|---:|
| SQL statements, `hybrid_keyword_1000` | 1,041 | 41 | -1,000 / -96.1% |
| Python 3.10 median, hosted SQLite runner | 222.794 ms | 35.301 ms | ~-84.2% observed |
| Baseline freeze, 100 items | 304 | 304 | unchanged |
| Traceability graph, 51 nodes | 106 | 106 | unchanged |
| PER DOCX render | 10 | 10 | unchanged |
| repository read baselines | 1 each | 1 each | unchanged |
| `create_object` | 3 | 3 | unchanged |
| `create_relation` | 2 | 2 | unchanged |

SQL statement count is the deterministic result. Hosted-runner timing is observational and remains non-gating.

## Mechanism confirmed

Before the change, keyword retrieval loaded the candidate object list and then executed one `get_version()` call for every scanned object. For the 1,000-object E2E workload, this accounted for exactly 1,000 avoidable SQL roundtrips.

The optimized path loads each non-deleted `RegulatoryObject` together with its exact `current_version` through one joined read query. The remaining 40 SQL statements in the 20-hit E2E scenario come from the existing security/correctness-sensitive exact-hit validation: two Object Store reads per returned hit.

The observed result therefore matches the performance hypothesis exactly:

- one joined keyword scan query;
- 20 hits x two existing validation reads;
- total = 41 statements.

## Functional evidence

The first complete optimized Python 3.10 CI run passed:

- Ruff lint and formatting;
- **557 tests passed, 1 skipped**;
- read performance baseline;
- write performance baseline;
- end-to-end performance baseline;
- specification linter;
- backlog generator.

The only remaining issue in that run was generated-file synchronization because adding this performance documentation changes the specification linter's scanned-file count. The final matrix rerun must therefore verify both supported Python runtimes after the generated report is synchronized.

## Preserved invariants

- Public keyword adapter API unchanged.
- `scan_limit` unchanged.
- Candidate ordering remains `updated_at DESC` before scoring.
- Soft-deleted objects remain excluded.
- `ai_draft` results remain excluded.
- Exact `current_version` payload is used for each candidate.
- Tokenization and canonical payload text generation unchanged.
- Keyword coverage and phrase bonus unchanged.
- Deterministic result sorting unchanged.
- Exact-version references returned in hits unchanged.
- `HybridRetrievalService._validate_hit()` unchanged.
- Vector and graph adapters unchanged.
- Retrieval remains read-only.

## Simplification pass

The end state contains one new persistence-layer read helper, `list_current_object_versions()`, because the optimized operation is a database projection rather than domain logic. No further abstraction is justified.

Deliberately not introduced:

- cache or cache invalidation;
- async/parallel database access;
- full-text search infrastructure;
- schema or index changes;
- database-specific keyword semantics;
- compatibility branches;
- temporary production instrumentation;
- changes to hit validation.

Moving the joined SQL into the domain retrieval service would reduce file count but worsen the architecture by leaking persistence details upward. The small DB-layer helper is therefore retained.

## Regression guards

`tests/test_ai_retrieval_performance.py` provides deterministic guards:

- keyword scanning across current versions executes exactly one SQL statement;
- hybrid keyword retrieval with ten hits executes at most 21 statements, preserving the current two-read-per-hit validation budget.

The persistent E2E harness also measures the 1,000-object workload and exposes future scaling regressions in CI artifacts.

## Residual performance opportunities

The remaining 40 hit-validation statements are now visible as a separate cost, but they are intentionally not optimized here. They enforce exact Object Store grounding and should only be changed in a new slice with an explicit validation-equivalence design and dedicated security regression tests.

Across the broader E2E baseline, the next independent database-roundtrip candidates are:

1. baseline creation: 304 statements for 100 items;
2. graph traceability: 106 statements for 51 nodes;
3. PER rendering: 10 statements and currently not material relative to the other two.

These are not part of this closure.

## Stop decision

The selected target is met exactly: the 1,000-object hybrid retrieval path is reduced from 1,041 to 41 statements without changing retrieval semantics or adding infrastructure complexity. No further retrieval optimization belongs in this slice.
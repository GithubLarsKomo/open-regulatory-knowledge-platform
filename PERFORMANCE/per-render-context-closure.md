# PERFORMANCE CLOSURE: PER Render Frozen-Context Reuse

## Result

**PASS** — the deterministic SQL budget for `per_render_docx` is reduced from **10 to 5 statements** without changing frozen-baseline semantics, rendered output behavior, artifact persistence, or supported formats.

## Verified behavior

The first CI verification run demonstrated on both Python 3.10 and Python 3.12:

- full pytest suite: 566 passed, 1 skipped
- `per_render_docx`: 5/5/5/5/5 SQL statements
- `baseline_create_100`: 6/6/6/6/6
- `graph_traceability_depth1_51`: 3/3/3/3/3
- `hybrid_keyword_1000`: 2/2/2/2/2
- repository read scenarios: 1 statement
- `create_object`: 3 statements
- `create_relation`: 2 statements
- Ruff lint and format checks pass

The Python 3.12 matrix was canceled only after the parallel Python 3.10 job reached the known generated-file drift caused by the newly added performance documentation; its tests and E2E harness had already completed and confirmed the same 5-statement budget.

## Change summary

1. `PERDraftService` loads report-baseline items once and reuses the immutable list for content, completeness and section coverage assembly.
2. Draft and render services derive the Baseline UUID from the already validated frozen report/draft context rather than loading the same Baseline row again.
3. Generated artifact UUIDs are captured after `flush()` and before `commit()`, avoiding a post-commit ORM refresh solely to build the response.
4. A deterministic query-budget regression test fixes the DOCX render budget at exactly five statements.

## Simplification pass

No temporary optimization infrastructure remains.

The final design deliberately contains only:

- one reused frozen-item list inside the existing draft service,
- UUID reuse inside the existing draft/render services,
- one permanent query-budget regression test.

Not introduced:

- cache or cache invalidation logic,
- async/parallel database reads,
- new service or repository abstraction,
- schema/index migration,
- template/rendering rewrite,
- trusted-context bypass,
- timing-based CI thresholds.

A broader `PerformanceReportService` refactor could theoretically reduce the path from five to four statements by sharing its initial BaselineItem read. That change is intentionally rejected for this slice because it crosses an additional service boundary for one statement, while `baseline_create_100` remains the larger measured path at six statements.

## Timing

Observed render timing improved in these CI samples, but timing remains non-gating because hosted-runner variance is material. The deterministic SQL statement count is the accepted performance regression guard.

## Stop rule

The target is met. Further PER render roundtrip optimization stops here unless new measurements show that this path is again a dominant bottleneck.

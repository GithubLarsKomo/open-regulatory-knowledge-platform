# TASK: Optimize PER Render Frozen-Context Reads

## Objective

Reduce `per_render_docx` from 10 SQL statements to 5 without changing deterministic output or frozen-baseline semantics.

## Baseline

- current E2E budget: 10 statements
- repeated reads of the same Baseline/BaselineItem context dominate the avoidable roundtrips
- DOCX serialization is in-memory and not currently evidenced as the structural hotspot

## Tasks

- [x] Reuse one `baseline_items` list for PER content, completeness and section coverage assembly.
- [x] Remove redundant PER draft Baseline reload.
- [x] Remove redundant PER renderer Baseline reload.
- [x] Capture artifact UUID before commit to avoid post-commit ORM refresh.
- [x] Add an exact 5-statement DOCX render regression guard.
- [ ] Run full Python 3.10 and 3.12 CI.
- [ ] Confirm persistent `per_render_docx` E2E count is exactly 5 on both runtimes.
- [ ] Confirm Baseline Create, Graph, Hybrid, read and write budgets are unchanged.
- [ ] Run simplification pass and document closure.
- [ ] Merge only after both runtime matrices are green.

## Functional gate

- deterministic identical bytes for repeated render
- checksum unchanged for identical bytes
- HTML/DOCX/PDF format tests remain green
- frozen content remains stable after live source changes
- exactly one artifact and one generation event per successful render
- failed PDF render persists no artifact
- unsupported format remains rejected

## Performance gate

- `per_render_docx`: exactly 5 statements
- `baseline_create_100`: unchanged at 6
- `graph_traceability_depth1_51`: unchanged at 3
- `hybrid_keyword_1000`: unchanged at 2
- repository read scenarios: unchanged at 1
- `create_object`: unchanged at 3
- `create_relation`: unchanged at 2

## Compatibility

- Python 3.10 and 3.12
- SQLAlchemy 2.x
- SQLite CI semantics
- no schema migration

## Out of scope

- sharing the first `PerformanceReportService` items read for a theoretical 4-statement render
- cross-request caching
- async/parallel rendering
- template redesign
- timing-based CI gates

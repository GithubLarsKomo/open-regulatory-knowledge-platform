# PERFORMANCE PLAN: PER Render Frozen-Context Reuse

## Goal

Reduce the deterministic SQL budget of the representative `per_render_docx` E2E workflow without changing rendered bytes, frozen-baseline semantics, artifact persistence, event logging, or supported formats.

## Baseline

`per_render_docx` currently uses 10 SQL statements per sample.

Static decomposition:

- `PerformanceReportService.build_report`: baseline read + baseline-items read
- `PERDraftService`: redundant baseline read plus three repeated baseline-items reads for content, completeness and section coverage
- `PERRenderService`: redundant baseline read
- artifact persistence: artifact insert + event insert
- post-commit access to the expired artifact triggers one refresh read

DOCX serialization itself is deterministic in-memory XML/ZIP generation and the current E2E timing does not show evidence that it is the structural bottleneck. Timing remains observational, not a CI gate.

## Root cause

The same immutable frozen baseline context is rehydrated several times inside one render request. These reads add no new information.

## Selected optimization

1. Let `PerformanceReportService.build_report()` keep its existing baseline + items reads.
2. Load report-baseline items once in `PERDraftService` and reuse that list for:
   - report content,
   - completeness,
   - canonical section coverage.
3. Derive the baseline UUID from the already validated draft/report context instead of re-reading the Baseline row in `PERDraftService` and `PERRenderService`.
4. Capture the generated artifact UUID after `flush()` and before `commit()` so the response does not trigger an expired-ORM refresh.

## Expected budget

- reads: 3
- inserts: 2
- total: **5 SQL statements**

Target: `per_render_docx` **10 -> 5** statements.

## Functional invariants

- output bytes and checksum remain deterministic for identical frozen baselines
- HTML, DOCX and PDF behavior remains unchanged
- only frozen baseline snapshots are used
- live object changes after freeze do not affect rendering
- invalid/unsupported render behavior remains unchanged
- exactly one `per_report` artifact and one `artifact_generated` event are persisted per successful render
- failed rendering persists no artifact

## Out of scope

- refactoring `PerformanceReportService` to share its baseline-items list with `PERDraftService` for a theoretical fourth statement
- template or visual redesign
- DOCX compression changes
- PDF renderer changes
- caching across requests
- schema/index changes
- timing-based CI thresholds

## Stop rule

Stop when the deterministic E2E budget is 5 statements, both Python runtime matrices are green, and no functional regressions appear. At that point Baseline Create (6 statements) becomes the largest measured E2E roundtrip path, so a broader report-service refactor for one additional statement is not justified without new evidence.

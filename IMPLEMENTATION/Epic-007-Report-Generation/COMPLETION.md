# Epic 007 — Report Generation MVP — Completion Record

## Status

Epic 007 / `TASK-REPORT-0001` is functionally complete and locally verified.

Final functional verification was performed on the `84d8ad2` master lineage after applying Ruff-only formatting locally:

- `pytest -q`: **488 passed, 1 warning**
- known warning: Starlette/httpx `TestClient` deprecation only
- `ruff check --select E9,F63,F7,F82 .`: **passed**
- `ruff format --check .`: **168 files already formatted**
- strict spec linter: **34 files / 168 IDs / 0 duplicates / 0 invalid formats / 0 undefined references**
- backlog generator: **5 foundation tasks / 14 generated tasks**
- `git diff --check`: only expected CRLF notices for generated Markdown artifacts

The Ruff formatter changed Python layout only; no semantic changes were introduced by that final formatting pass.

## Requirements covered

### `REP-PER-0001` — Generate a PER draft from approved structured data

Implemented through frozen Performance Evaluation baselines, derived PER Report baselines, canonical `PERDraftPayload`, and persisted governed PER Report objects.

Key components:

- `PerformanceReportService`
- `PERReportBaselineService`
- `PERDraftService`
- `PERReportObjectService`
- `PERReportObjectPayload`

The governed persisted Report uses Core `object_type='report'` and stores the exact frozen canonical draft plus SHA-256.

### `REP-PER-0002` — Include traceability to source objects

The PER draft contains exact source object UUID/version references for Performance Result, Study, Claims, statistical sources, frozen content, completeness context, and canonical section coverage.

Cross-domain Benefit-Risk/PMPF inputs are accepted only through explicit exact references and canonical provenance relations.

### `REP-PER-0003` — Distinguish approved content from AI-generated draft content

Content provenance is explicit:

- approved source content: `origin='approved_source'`, `review_status='source_approved'`
- AI draft content: `origin='ai_draft'`, `review_status='unapproved_draft'`, mandatory `model_id`

AI draft text is first frozen as versioned `report_content`; transient AI text is not accepted by draft generation.

### `REP-PER-0004` — Include a completeness report listing missing evidence

The existing deterministic `PerformanceClaimGapReport` is evaluated once at PER Report baseline creation and persisted as `report_completeness`.

Draft generation reads only the frozen completeness snapshot. Later live Product/Claim/Evidence changes cannot alter a previously frozen report baseline.

### `REP-PER-0005` — Reproduce the PER from a baseline

All canonical Report generation paths are baseline-only after freeze.

The derived governed draft schema is `per-draft-1.3`. Repeated generation from the same baseline is deterministic.

## Canonical ten-section PER structure

Every derived PER Report baseline freezes exactly one `per-section-coverage-1.0` snapshot containing exactly these ordered sections:

1. `cover_page`
2. `intended_purpose`
3. `scientific_validity`
4. `analytical_performance`
5. `clinical_performance`
6. `claims_and_evidence`
7. `risk_benefit_analysis`
8. `pmpf_summary`
9. `traceability_appendix`
10. `completeness_report`

Each section is either `available` or `missing` with a section-specific stable gap code. Missing regulatory content is never invented.

## Cross-domain Risk / PMPF provenance

Risk-Benefit and PMPF are never auto-selected from live state.

Benefit-Risk requires:

- explicit approved/effective exact `benefit_risk` reference
- exact Residual Risk Evaluation
- exact Risk Analysis
- exact Risk Policy
- residual evaluation with `acceptable=False`
- `benefit_risk_required=True`
- exact `benefit_risk_for`, `uses_risk_policy`, `residual_of`, and residual `uses_risk_policy` relations
- Risk Analysis pinned to the frozen Product

PMPF requires:

- explicit approved/effective Risk Impact Assessment
- exact `post_market_information` with `source_type='pmpf'`
- exact Risk Analysis
- canonical assessment `derived_from` relations with roles
- information `impacts_risk`
- Risk Analysis `informed_by`
- Risk Analysis pinned to the frozen Product

Generic-object bypass regressions verify that formally shaped but non-canonical objects cannot enter the PER baseline.

## Persisted Report lifecycle and governance

Persisted PER Reports use Core versioning/lifecycle semantics:

- create → `draft`
- submit → `in_review`
- approve → `approved`
- optional later Core progression to `effective` / `obsolete`

Governance protections:

- Report owner may not approve their own Report
- author of the current Report version may not approve that version
- approved/effective/obsolete Report versions are immutable
- draft regeneration creates a new version under the same `report_uuid`
- post-approval regeneration creates a new Report aggregate with an exact predecessor reference
- canonical JSON and SHA-256 are validated on every persisted Report read
- governed Report creation requires `per-report-object-1.0` containing a valid `per-draft-1.3`

The generic Core REST API cannot bypass the governed PER workflow:

- generic creation of `object_type='report'` is blocked
- generic Report version creation is blocked
- generic transitions to `in_review` or `approved` are blocked

Read access, version history, and audit events remain available through Core REST APIs.

## Deterministic output formats

The same frozen canonical draft can be rendered as:

- JSON
- HTML
- DOCX
- PDF

`PERRenderService` creates exactly one `GeneratedArtifact` with `artifact_type='per_report'` per successful render call and records the exact SHA-256 of returned bytes.

Rendering does not create a hidden intermediate `per_draft` artifact.

DOCX uses deterministic OOXML ZIP metadata. PDF uses deterministic PDF 1.4 / WinAnsi output and explicitly rejects unsupported characters rather than silently corrupting them.

## API surface

Key PER Report endpoints include:

- `POST /api/v1/per-reports/baselines`
- `POST /api/v1/per-reports/{baseline_uuid}/drafts`
- `POST /api/v1/per-reports/{baseline_uuid}/renders/{html|docx|pdf}`
- `POST /api/v1/per-reports`
- `GET /api/v1/per-reports/{report_uuid}`
- `GET /api/v1/per-reports/{report_uuid}/canonical-json`
- `POST /api/v1/per-reports/{report_uuid}/submit`
- `POST /api/v1/per-reports/{report_uuid}/approve`
- `POST /api/v1/per-reports/{report_uuid}/regenerate`

## Completed issues

- #1 — Epic 007 umbrella / baseline-pinned deterministic PER generation
- #20 — reproducible PER Draft Manifest and Traceability Appendix
- #21 — approved vs AI draft content provenance
- #22 — frozen Completeness Report
- #23 — deterministic HTML/DOCX/PDF rendering
- #24 — persisted PER Report aggregate and lifecycle
- #26 — canonical ten-section PER coverage

## Important implementation / hardening commits

Representative commits include:

- `cd48d7b`, `1f9989b`, `01ec839` — side-effect-free draft builder, draft service and API
- `f0a995e`, `8501a53` — frozen report content / exact AI content provenance
- `29a5457`, `0a745b2` — frozen completeness
- `31ebe90`, `6b65552` — deterministic render service/API
- `1e8a96a`, `45d8a37` — persisted Report aggregate/lifecycle
- `204afb9`, `85fca25`, `794986e`, `8e776b7` — ten-section coverage and baseline integration
- `f2e2773`, `b918410` — canonical cross-domain relation gate / generic Benefit-Risk bypass regression
- `8483bcb`, `5c144d5` — Residual Risk provenance hardening
- `1819848`, `7b531cc`, `5ab12a0`, `74fdd44` — strict draft/section/report payload integrity contracts
- `70c8755`, `fb77e5f` — generic Core API Report bypass guards
- `6b4b86b`, `84d8ad2` — update legacy cross-domain fixtures to the strict Residual Risk provenance contract

## Audit / reproducibility properties

The completed Epic preserves these invariants:

- exact UUID/version pinning
- deterministic canonical JSON
- deterministic output byte generation
- SHA-256 integrity checks
- audit events for generated artifacts and lifecycle transitions
- no live source auto-selection during draft/render regeneration
- no invented regulatory content
- no AI-generated content represented as approved
- no generic Core API bypass of governed Report creation/versioning/approval
- four-eyes approval
- immutable approved Report versions
- explicit structured gaps when required evidence or sections are missing

## Known non-blocking item

The full suite emits one Starlette/httpx deprecation warning from `fastapi.testclient`. It does not affect Epic 007 functionality or regulatory traceability behavior.

## Completion decision

Epic 007 is accepted as functionally complete based on the verified **488 passed** full-suite gate and the strict lint/spec/backlog checks above.

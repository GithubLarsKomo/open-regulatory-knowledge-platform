# SPEC-PER.md

## Purpose

Define automated generation, persistence and reproducible rendering of the Performance Evaluation Report.

## Scope

The PER capability covers:

- automated PER draft generation from structured data;
- canonical ten-section PER coverage;
- traceability appendix generation;
- explicit approved-source vs AI-draft content provenance;
- frozen completeness gap reporting;
- explicit frozen Risk-Benefit and PMPF context;
- baseline-based reproducibility;
- a persisted, versioned PER Report aggregate with governed review/approval lifecycle;
- deterministic JSON, HTML, DOCX and PDF output projections.

## Stakeholders

- Regulatory Authors — initiate and review PER drafts
- QM Reviewers — review PER content
- Regulatory Approvers — approve final report content
- Auditors — review traceability, lifecycle, section coverage and completeness

## Inputs

- Intended purpose
- Claims
- Scientific validity
- Analytical performance
- Clinical performance
- Literature
- Risk-benefit conclusions
- PMS/PMPF data
- State of the art

## Domain Model

### Canonical PER Report Structure

Every derived PER Report baseline freezes exactly one section-coverage snapshot containing the following ten sections in this exact order:

| Section ID | Section | Primary source |
|---|---|---|
| `cover_page` | Cover Page | Frozen Product metadata |
| `intended_purpose` | Intended Purpose | Frozen Product intended purpose |
| `scientific_validity` | Scientific Validity | Frozen scientific-validity Performance Results |
| `analytical_performance` | Analytical Performance | Frozen analytical Performance Results |
| `clinical_performance` | Clinical Performance | Frozen clinical Performance Results |
| `claims_and_evidence` | Claims and Evidence | Frozen Claim/Evidence context |
| `risk_benefit_analysis` | Risk-Benefit Analysis | Explicit approved/effective Benefit-Risk source(s) |
| `pmpf_summary` | PMPF Summary | Explicit approved/effective PMPF Risk-Impact Assessment source(s) |
| `traceability_appendix` | Traceability Appendix | Frozen Performance provenance context |
| `completeness_report` | Completeness Report | Frozen Performance Claim gap analysis |

Each canonical section is represented as `available` or `missing`. Missing source content is never invented. A missing section carries a stable machine-readable section-gap code. An available section carries only structured data and exact frozen `VersionedObjectReference` source references.

### Canonical PER Draft Manifest

Report generation consumes frozen baselines. It does not reselect live Product, Claim, Evidence, Study, Risk, post-market, report-content, completeness or section-coverage payloads during PER composition.

`PerformanceReportService.build_report()` is the side-effect-free baseline-only builder for frozen scientific-validity, analytical-performance and clinical-performance sections. `PERDraftService.build_draft()` composes the complete canonical PER draft without persisting an intermediate artifact.

A draft generated directly from a Performance Evaluation baseline retains schema `per-draft-1.1`. It has no report-level completeness or canonical section-coverage snapshot.

A draft generated from a derived PER Report baseline uses schema `per-draft-1.3` and contains:

- the exact frozen Product snapshot;
- the deterministic Performance section manifest;
- explicit text `content_blocks` with provenance and review status;
- a frozen `completeness_report` with exact snapshot reference;
- frozen canonical `section_coverage` with exactly ten ordered sections and exact snapshot reference;
- a deterministic traceability appendix;
- the originating baseline UUID/name/description.

A derived Report draft is invalid when exactly one of completeness or section coverage is present. The two report-level snapshots are frozen and consumed as one governed report context.

Each traceability entry pins the exact frozen versions of Performance Result Evidence, source Performance Study, supported Claim(s), and statistical-source Evidence where present.

The canonical draft JSON is serialized with deterministic key ordering and compact separators. The JSON draft endpoint records SHA-256 plus a `GeneratedArtifact` with `artifact_type='per_draft'` and `format='json'`.

### Content Provenance

PER text uses explicit provenance classes:

- `approved_source` / `source_approved` — text already present in an approved frozen source object. In the current contract this is the exact `interpretation` text of an approved frozen Performance Result.
- `ai_draft` / `unapproved_draft` — externally generated AI text that has not been approved.

An `approved_source` block cannot carry a model identifier or separate content reference. An `ai_draft` block must carry a non-empty `model_id`, exact regulatory `source_refs`, and an exact frozen `content_ref` to its `report_content` object version. Report generation never promotes AI draft text to approved content.

Epic 007 does not invoke an AI model. External AI output enters the report only while creating a derived PER Report baseline.

### Derived PER Report Baseline

A derived PER Report baseline is the authoring baseline for report-level content. AI draft blocks are optional; completeness and canonical section-coverage snapshotting are mandatory.

Creation follows this contract:

1. validate an existing Performance Evaluation baseline through the side-effect-free Performance report builder;
2. obtain the exact Product version frozen in that baseline;
3. execute the existing `PerformanceClaimGapService.evaluate_product()` once during report-baseline creation;
4. require the evaluated Product version to equal the Product version frozen in the source Performance Evaluation baseline;
5. validate any explicitly supplied cross-domain Risk-Benefit and PMPF references and their exact versioned provenance;
6. persist the complete `PerformanceClaimGapReport` as strict draft `report_completeness` with schema `per-completeness-1.0`;
7. freeze every exact Claim and Evidence version referenced by the gap report, de-duplicated with existing Performance baseline items;
8. build and persist exactly one strict `report_section_coverage` object with schema `per-section-coverage-1.0` and the exact ten canonical sections;
9. freeze all explicitly selected valid Risk-Benefit/PMPF source objects and their exact supporting context;
10. if AI draft blocks are supplied, validate their exact source references against the original Performance Evaluation baseline and persist each as strict draft `report_content`;
11. atomically freeze all original Performance items, completeness context, section coverage, explicit cross-domain context and any exact `report_content` versions into a new Baseline.

The source must be a raw Performance Evaluation baseline, not another report baseline. AI block IDs may not use the reserved `approved:` prefix used for source-approved content blocks.

### Frozen Completeness Report

`PERCompletenessSnapshotPayload` contains:

- schema version `per-completeness-1.0`;
- source Performance Evaluation baseline UUID;
- the exact deterministic `PerformanceClaimGapReport` from `REQ-PERF-0006`;
- the user who froze the snapshot.

The gap report retains the existing stable rule codes and does not introduce a second sufficiency policy. Claim/Evidence versions named by its findings are frozen into the derived report baseline even when they were absent from the original Performance baseline because, for example, a Claim has no supporting Performance Result.

PER draft generation does **not** call the live Performance gap evaluator. It reads exactly one frozen `report_completeness.snapshot_json`, verifies that its Product matches the frozen PER Product, verifies that every referenced Claim/Evidence version is present in the same baseline, and exposes the result as `completeness_report` with an exact `snapshot_ref`.

### Frozen Canonical Section Coverage

`PERSectionCoverageSnapshotPayload` contains:

- schema version `per-section-coverage-1.0`;
- source Performance Evaluation baseline UUID;
- exactly ten `PERCanonicalSection` entries in canonical order;
- the user who froze the snapshot.

Section status/gap semantics are deterministic:

- Cover Page is available from the frozen Product snapshot.
- Intended Purpose is available only when the frozen Product contains a non-blank `intended_purpose`; otherwise it carries `PER-SECTION-INTENDED-PURPOSE-MISSING`.
- Scientific Validity, Analytical Performance and Clinical Performance are available only when the corresponding frozen Performance section contains Results; otherwise they carry their respective `PER-SECTION-*-MISSING` code.
- Claims and Evidence is available only when Performance-relevant frozen Claim context exists; otherwise it carries `PER-SECTION-CLAIMS-EVIDENCE-MISSING`.
- Risk-Benefit is available only from explicitly supplied valid approved/effective sources; otherwise it carries `PER-SECTION-RISK-BENEFIT-MISSING`.
- PMPF Summary is available only from explicitly supplied valid approved/effective PMPF assessment sources; otherwise it carries `PER-SECTION-PMPF-MISSING`.
- Traceability Appendix is available only when frozen Performance provenance context exists; otherwise it carries `PER-SECTION-TRACEABILITY-MISSING`.
- Completeness Report is always available in a valid derived Report baseline and references the exact frozen completeness snapshot.

No cross-domain source is selected automatically from live data.

#### Risk-Benefit source contract

Each requested `benefit_risk` reference must identify the exact approved/effective version. Its strict `BenefitRiskAnalysisPayload` is parsed, and the exact referenced Risk Analysis, Residual Risk Evaluation and Risk Policy context are frozen. The Benefit-Risk source must retain its exact canonical `benefit_risk_for` and `uses_risk_policy` relations. Its Risk Analysis must be pinned through an exact Product/Risk relation to the same Product version frozen in the Performance Evaluation baseline.

#### PMPF source contract

Each requested PMPF source is an exact approved/effective `risk_impact_assessment` version with a completed outcome. The assessment must point to exact `post_market_information` whose `source_type='pmpf'` and to an exact Risk Analysis. Assessment and information must reference the same Risk Analysis. Canonical exact relations must exist for assessment `derived_from` information (`role='impact_assessment_source'`), assessment `derived_from` Risk Analysis (`role='assessed_risk'`), information `impacts_risk` Risk Analysis and Risk Analysis `informed_by` information. The Risk Analysis must be pinned to the frozen Product version.

At draft generation, exactly one frozen section-coverage snapshot is read. Every section source reference must exist in the same baseline and the Cover Page must include the exact frozen Product. Missing, duplicate or externally referencing coverage snapshots are rejected.

Later live Product, Claim, Evidence, Risk, PMPF or relation changes do not alter the frozen section coverage of the same Report baseline.

### Persisted PER Report Aggregate

A governed PER Report is persisted in the existing Core RegulatoryObject store with `object_type='report'`. No separate report table is required.

`PERReportObjectPayload` schema `per-report-object-1.0` stores:

- `report_type`: `PER` or `PER-addendum`;
- the exact frozen Product reference;
- mandatory derived PER Report `baseline_uuid`;
- the exact canonical `PERDraftPayload` snapshot;
- SHA-256 of the canonical draft JSON;
- optional exact predecessor Report reference.

Persisted Report creation requires a derived Report baseline with frozen completeness and exactly ten canonical frozen sections (`per-draft-1.3`). A raw Performance Evaluation baseline is sufficient for draft-manifest generation but not for creation of a governed persisted PER Report.

The persisted payload validates that Product and Baseline match the embedded frozen draft and that its SHA-256 matches a canonical reserialization. Retrieval therefore detects corrupted or inconsistent persisted report payloads.

The stable `report_uuid` is the Core RegulatoryObject UUID. Lifecycle uses the existing Core state machine:

- creation → `draft`;
- submit → `in_review`;
- approve → `approved`;
- approved/effective/obsolete versions are immutable through the Core repository.

Self-approval is forbidden for the Report owner and the author of the current Report version.

Regeneration rules:

- while `draft`, regeneration from another valid derived Report baseline creates a new ObjectVersion on the same `report_uuid`;
- while `in_review` or `rejected`, regeneration is rejected until the lifecycle is resolved;
- after `approved`, `effective` or `obsolete`, regeneration creates a new Report aggregate in `draft` with an exact predecessor Report UUID/version reference.

The canonical-JSON retrieval endpoint reads the persisted Report snapshot; it does not regenerate from live source objects.

### Deterministic Document Rendering

HTML, DOCX and PDF are projections of `PERDraftService.build_draft()` and therefore consume the same frozen baseline-only manifest.

- HTML is deterministic UTF-8 semantic output.
- DOCX is a deterministic minimal OOXML package with fixed package metadata and entry ordering.
- PDF is a deterministic PDF 1.4 text representation using Helvetica/WinAnsi. Characters outside Windows-1252 are rejected rather than silently changed.

Each successful document render records exactly one `GeneratedArtifact` with `artifact_type='per_report'`, requested format and SHA-256 over the exact returned bytes, plus an `artifact_generated` audit event. Rendering does not create an intermediate `per_draft` artifact.

## Interfaces

- Product Service — product metadata and intended purpose
- Claim Service — claim data
- Evidence Service — evidence links and quality ratings
- Performance Service — study data and results
- Performance Gap Service — evaluated once during report-baseline freeze
- Performance Report Service — side-effect-free frozen Performance section composition
- PER Report Baseline Service — atomically freezes completeness, canonical section coverage, explicit cross-domain context and optional external AI draft content
- PER Section Coverage Service — validates explicit Risk-Benefit/PMPF context and builds the exact ten-section snapshot
- PER Draft Service — canonical baseline-only PER draft, section coverage, completeness, content provenance and exact traceability appendix
- PER Report Object Service — stable persisted Report identity, versioning, lifecycle and canonical snapshot retrieval
- PER Render Service — deterministic HTML/DOCX/PDF projection and artifact audit
- Risk Service — source of explicitly selected approved Benefit-Risk context
- Post-Market Service — source of explicitly selected governed PMPF impact context
- AI Service — may provide external draft text but is not invoked by Report Generation

## Data Model

### PER Report

| Field | Type | Description |
|---|---|---|
| report_uuid | UUID | Stable Core RegulatoryObject identifier |
| object_version | INTEGER | Version of the persisted Report aggregate |
| report_type | VARCHAR | `PER` / `PER-addendum` |
| product | VersionedObjectReference | Exact Product UUID/version from frozen draft |
| baseline_uuid | UUID | Derived Report baseline snapshot reference |
| lifecycle_state | VARCHAR | `draft` / `in_review` / `approved` plus Core post-approval states |
| draft | PERDraftPayload | Exact frozen canonical report snapshot |
| canonical_checksum_sha256 | SHA-256 | Integrity checksum of canonical draft JSON |
| predecessor_report | VersionedObjectReference? | Prior approved Report when regeneration creates a successor aggregate |

### PER Draft Manifest

| Field | Type | Description |
|---|---|---|
| schema_version | VARCHAR | `per-draft-1.1` for raw Performance baseline; `per-draft-1.3` for derived Report baseline |
| baseline_uuid | UUID | Frozen Performance or derived PER Report baseline |
| product | Snapshot | Exact frozen Product version and payload |
| performance_sections | PerformanceReportPayload | Frozen scientific/analytical/clinical section manifest |
| content_blocks | List[PERContentBlock] | Explicit approved-source / AI-draft text provenance |
| completeness_report | PERCompletenessReport? | Frozen gap report and exact completeness snapshot reference |
| section_coverage | PERSectionCoverageReport? | Exact frozen ten-section coverage and snapshot reference |
| traceability_appendix | List[PERTraceabilityEntry] | Exact frozen Result/Study/Claim/source version references |

### PER Section Coverage Snapshot

| Field | Type | Description |
|---|---|---|
| schema_version | VARCHAR | `per-section-coverage-1.0` |
| source_performance_baseline_uuid | UUID | Source Performance Evaluation baseline |
| sections | List[PERCanonicalSection] | Exactly ten ordered canonical section coverage entries |
| owner_user_id | VARCHAR | User freezing canonical report section coverage |

### PER Canonical Section

| Field | Type | Description |
|---|---|---|
| section_id | VARCHAR | One of the ten canonical section identifiers |
| status | VARCHAR | `available` / `missing` |
| source_refs | List[VersionedObjectReference] | Exact frozen regulatory sources for the section |
| data | JSON | Frozen structured section data; never invented missing narrative |
| gap_code | VARCHAR? | Stable missing-section code; absent for available sections |

### PER Report Content

| Field | Type | Description |
|---|---|---|
| block_id | VARCHAR | Stable content-block identifier |
| section_type | VARCHAR | scientific_validity / analytical_performance / clinical_performance |
| text | TEXT | Frozen text content |
| origin | VARCHAR | `ai_draft` for external AI content objects |
| review_status | VARCHAR | `unapproved_draft` for AI content objects |
| model_id | VARCHAR | External model identifier |
| source_performance_baseline_uuid | UUID | Source Performance Evaluation baseline |
| source_refs | List[VersionedObjectReference] | Exact sources already frozen in source baseline |
| owner_user_id | VARCHAR | User accepting/freezing external draft content |

### PER Completeness Snapshot

| Field | Type | Description |
|---|---|---|
| schema_version | VARCHAR | `per-completeness-1.0` |
| source_performance_baseline_uuid | UUID | Source Performance Evaluation baseline |
| gap_report | PerformanceClaimGapReport | Exact frozen output of existing Performance gap analysis |
| owner_user_id | VARCHAR | User freezing report completeness |

## Workflow

- data collection → Performance Evaluation baseline → derived PER Report baseline with frozen completeness, ten-section coverage, explicit cross-domain context and optional AI draft content → canonical PER draft → persisted PER Report `draft` → `in_review` → `approved` → optional Core post-approval states;
- regeneration from the same derived baseline never re-evaluates completeness or reselects cross-domain section sources;
- draft regeneration versions the same Report aggregate;
- post-approval regeneration creates a successor Report aggregate and preserves the approved predecessor;
- document rendering is reproducible from the frozen baseline and records checksummed artifacts.

## Security

- PER generation requires Regulatory Author role at the authorization layer
- PER approval requires Regulatory Approver role at the authorization layer
- PER content is reproducible from baseline for audit verification
- Report generation shall not bypass Product, Claim, Evidence, Performance, Risk or PMPF approval/provenance decisions; it consumes their frozen outputs
- AI-generated text remains explicitly unapproved until governed human review changes that status
- PER Report self-approval by the Report owner/current-version author is forbidden

## AI Support

- AI may draft PER sections from structured data outside the Report Generation component
- externally generated AI text must be frozen as `report_content` before report generation
- AI may propose literature summaries for scientific validity sections
- AI-generated content is explicitly flagged in the output and is never silently treated as approved
- completeness and canonical section-coverage reporting are deterministic and do not depend on AI

## Acceptance Criteria

- A PER draft can be generated from approved structured Product/Performance data.
- The canonical JSON-first PER draft can be generated from a frozen baseline without live regulatory-object payload reads.
- Generated PER includes traceability to exact frozen source object versions.
- Derived Report drafts contain exactly ten canonical section-coverage entries in deterministic order.
- Missing canonical sections are represented explicitly with stable gap codes and no invented regulatory content.
- Approved source text and AI-generated draft text are explicitly distinguishable in the manifest.
- External AI draft text is frozen into a derived report baseline before generation.
- A derived PER Report baseline freezes exactly one completeness snapshot and exactly one canonical section-coverage snapshot generated for the matching frozen Product version.
- Missing/insufficient Performance evidence is exposed using the stable gap codes from the existing Performance gap analysis.
- Risk-Benefit and PMPF sections use only explicitly supplied, approved/effective, exact-version sources with canonical provenance tied to the frozen Product; absent sources remain explicit gaps.
- Repeated generation from the same report baseline does not re-evaluate completeness or reselect cross-domain sources and yields identical canonical JSON/checksum after later live changes.
- A stable persisted PER Report aggregate references exact Product and derived baseline versions.
- Persisted canonical JSON is retrieved from the stored Report snapshot and remains independent of later live source changes.
- Approved Reports are immutable; regeneration after approval creates a successor Report rather than mutating the approved object.
- HTML, DOCX and PDF outputs are deterministic projections of the same frozen canonical manifest.

## Open Questions

- Should PER support multi-language generation?
- How to handle large evidence sets in the traceability appendix?
- Should PER generation support incremental updates beyond the current `PER-addendum` report type?

### REP-PER-0001
The system shall generate a PER draft from approved structured data.

### REP-PER-0002
The generated PER shall include traceability to source objects.

### REP-PER-0003
The PER shall distinguish approved text from AI-generated draft text.

### REP-PER-0004
The PER shall contain a completeness report listing missing evidence.

### REP-PER-0005
The PER shall be reproducible from a baseline.

## Output Formats

- DOCX
- PDF
- HTML
- JSON

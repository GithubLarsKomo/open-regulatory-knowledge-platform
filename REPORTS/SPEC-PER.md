# SPEC-PER.md

## Purpose

Define automated generation of the Performance Evaluation Report.

## Scope

The PER generation covers:

- Automated PER draft generation from structured data
- PER section composition (scientific validity, analytical performance, clinical performance)
- Traceability appendix generation
- Explicit approved-source vs AI-draft content provenance
- Completeness gap analysis
- Baseline-based reproducibility

## Stakeholders

- Regulatory Authors — initiate and review PER drafts
- QM Reviewers — approve PER content
- Regulatory Approvers — sign off on final report
- Auditors — review traceability and completeness

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

### PER Report Structure

| Section | Source |
|---|---|
| Cover Page | Product metadata |
| Intended Purpose | Product domain |
| Scientific Validity | Performance studies, literature |
| Analytical Performance | Performance studies |
| Clinical Performance | Performance studies, literature |
| Claims and Evidence | Claim and Evidence domains |
| Risk-Benefit Analysis | Risk domain |
| PMPF Summary | PMS/PMPF data |
| Traceability Appendix | All source objects |
| Completeness Report | Gap analysis |

### Canonical PER Draft Manifest

The Report Generation capability consumes frozen baselines. It does not reselect live Product, Claim, Evidence, Study or report-content payloads during PER composition.

`PerformanceReportService.build_report()` is the side-effect-free baseline-only builder for the frozen scientific-validity, analytical-performance and clinical-performance section payload. The existing Performance section-generation endpoint continues to persist its own `performance_evaluation_sections` artifact, while the PER Draft Service may reuse the builder without creating that intermediate artifact.

`PERDraftPayload` has schema version `per-draft-1.1` and contains:

- the exact frozen Product snapshot;
- the deterministic Performance section manifest;
- explicit text `content_blocks` with provenance and review status;
- a deterministic traceability appendix;
- the originating baseline UUID/name/description.

Each traceability entry pins the exact frozen versions of:

- Performance Result Evidence;
- source Performance Study;
- supported Claim(s);
- statistical-source Evidence, where present.

The canonical draft JSON is serialized with deterministic key ordering and compact separators, SHA-256 hashed, and recorded as a `GeneratedArtifact` with `artifact_type='per_draft'`, `format='json'`, the source baseline UUID and an `artifact_generated` audit event.

### Content Provenance

PER text uses explicit provenance classes:

- `approved_source` / `source_approved` — text already present in an approved frozen source object. In the current contract this is the exact `interpretation` text of an approved frozen Performance Result.
- `ai_draft` / `unapproved_draft` — externally generated AI text that has not been approved.

An `approved_source` block cannot carry a model identifier. An `ai_draft` block must carry a non-empty `model_id` and is never promoted to approved content by report generation.

Epic 007 does not invoke an AI model. External AI output enters the report only while creating a derived PER Report baseline.

### Derived PER Report Baseline

A derived PER Report baseline preserves report reproducibility when external AI draft text is used:

1. an existing Performance Evaluation baseline is validated through the side-effect-free Performance report builder;
2. every AI draft block must provide a stable block ID, target Performance section, non-empty text, model ID and one or more exact source references;
3. every AI source reference must already exist in the source Performance Evaluation baseline;
4. duplicate AI block IDs and duplicate exact source references are rejected;
5. each AI block is persisted as a strict draft `report_content` RegulatoryObject with `origin='ai_draft'` and `review_status='unapproved_draft'`;
6. a new Baseline atomically freezes all original Performance baseline object versions plus the exact new `report_content` versions.

The derived baseline cannot use another report baseline as its source. AI block IDs may not use the reserved `approved:` prefix used for source-approved content blocks.

PER generation accepts no transient AI text. It reads only the frozen derived baseline. Later versions of regulatory source objects or `report_content` objects therefore do not alter regenerated canonical JSON or checksum.

Completeness-report snapshotting, report lifecycle/versioning and DOCX/PDF/HTML rendering remain later Epic 007 responsibilities.

## Interfaces

- Product Service — product metadata and intended purpose
- Claim Service — claim data
- Evidence Service — evidence links and quality ratings
- Performance Service — study data and results
- Performance Report Service — side-effect-free frozen Performance section composition
- PER Report Baseline Service — atomically freezes external AI draft content with exact Performance context
- PER Draft Service — canonical baseline-only PER draft, content provenance and exact traceability appendix
- Risk Service — risk-benefit analysis
- AI Service — may provide external draft text but is not invoked by Report Generation
- Template Service — DOCX/PDF template rendering

## Data Model

### PER Report

| Field | Type | Description |
|---|---|---|
| report_uuid | UUID | Stable identifier |
| product_uuid | UUID | Subject product |
| report_type | VARCHAR | PER / PER-addendum |
| baseline_uuid | UUID | Baseline snapshot reference |
| lifecycle_state | VARCHAR | draft / in_review / approved |
| generated_at | DATETIME | Generation timestamp |
| generated_by | VARCHAR | User who initiated generation |

### PER Draft Manifest

| Field | Type | Description |
|---|---|---|
| schema_version | VARCHAR | `per-draft-1.1` |
| baseline_uuid | UUID | Frozen Performance or derived PER Report baseline |
| product | Snapshot | Exact frozen Product version and payload |
| performance_sections | PerformanceReportPayload | Frozen scientific/analytical/clinical section manifest |
| content_blocks | List[PERContentBlock] | Explicit approved-source / AI-draft text provenance |
| traceability_appendix | List[PERTraceabilityEntry] | Exact frozen Result/Study/Claim/source version references |
| checksum | SHA-256 | Deterministic checksum of canonical JSON |

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

## Workflow

- PER lifecycle: data collection → draft generation → review → approval → publication
- Frozen Performance Evaluation baseline → optional derived report baseline with frozen AI draft content → canonical PER draft manifest → later completeness enrichment → document rendering
- Report regeneration triggers version bump
- Approved reports are immutable

## Security

- PER generation requires Regulatory Author role
- PER approval requires Regulatory Approver role
- PER content is reproducible from baseline for audit verification
- Report generation shall not bypass Product, Claim, Evidence, Performance or Risk approval decisions; it consumes their frozen outputs
- AI-generated text remains explicitly unapproved until a later governed human-review workflow changes that status

## AI Support

- AI may draft PER sections from structured data outside the Report Generation component
- externally generated AI text must be frozen as `report_content` before report generation
- AI may propose literature summaries for scientific validity sections
- AI may identify evidence gaps for the completeness report
- AI-generated content is explicitly flagged in the output and is never silently treated as approved

## Acceptance Criteria

- A PER draft can be generated from approved product data.
- The canonical JSON-first PER draft can be generated from a frozen baseline without live regulatory-object payload reads.
- Generated PER includes traceability to exact frozen source object versions.
- Approved source text and AI-generated draft text are explicitly distinguishable in the manifest.
- External AI draft text is frozen into a derived report baseline before generation.
- Repeated generation from the same baseline yields identical canonical JSON and checksum.
- Missing evidence is reported in the completeness section.
- Report can be reproduced from a stored baseline.

## Open Questions

- Should PER support multi-language generation?
- How to handle large evidence sets in the traceability appendix?
- Should PER generation support incremental updates (addendum)?

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

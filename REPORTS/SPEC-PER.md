# SPEC-PER.md

## Purpose

Define automated generation of the Performance Evaluation Report.

## Scope

The PER generation covers:

- Automated PER draft generation from structured data
- PER section composition (scientific validity, analytical performance, clinical performance)
- Traceability appendix generation
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

The first Report Generation slice consumes an existing frozen Performance Evaluation baseline created by the Performance domain. It does not reselect live Product, Claim, Evidence or Study payloads.

`PerformanceReportService.build_report()` is the side-effect-free baseline-only builder for the frozen scientific-validity, analytical-performance and clinical-performance section payload. The existing Performance section-generation endpoint continues to persist its own `performance_evaluation_sections` artifact, while the PER Draft Service may reuse the builder without creating that intermediate artifact.

`PERDraftPayload` has schema version `per-draft-1.0` and contains:

- the exact frozen Product snapshot;
- the deterministic Performance section manifest;
- a deterministic traceability appendix;
- the originating baseline UUID/name/description.

Each traceability entry pins the exact frozen versions of:

- Performance Result Evidence;
- source Performance Study;
- supported Claim(s);
- statistical-source Evidence, where present.

The canonical draft JSON is serialized with deterministic key ordering and compact separators, SHA-256 hashed, and recorded as a `GeneratedArtifact` with `artifact_type='per_draft'`, `format='json'`, the source baseline UUID and an `artifact_generated` audit event.

The first slice does not yet add AI-generated prose, completeness-report snapshotting, report lifecycle/versioning, or DOCX/PDF/HTML rendering. Those remain later Epic 007 responsibilities.

## Interfaces

- Product Service — product metadata and intended purpose
- Claim Service — claim data
- Evidence Service — evidence links and quality ratings
- Performance Service — study data and results
- Performance Report Service — side-effect-free frozen Performance section composition
- PER Draft Service — canonical baseline-only PER draft and exact traceability appendix
- Risk Service — risk-benefit analysis
- AI Service — draft generation assistance
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
| schema_version | VARCHAR | `per-draft-1.0` |
| baseline_uuid | UUID | Frozen Performance Evaluation baseline |
| product | Snapshot | Exact frozen Product version and payload |
| performance_sections | PerformanceReportPayload | Frozen scientific/analytical/clinical section manifest |
| traceability_appendix | List[PERTraceabilityEntry] | Exact frozen Result/Study/Claim/source version references |
| checksum | SHA-256 | Deterministic checksum of canonical JSON |

## Workflow

- PER lifecycle: data collection → draft generation → review → approval → publication
- Frozen Performance Evaluation baseline → canonical PER draft manifest → later completeness/AI provenance enrichment → document rendering
- Report regeneration triggers version bump
- Approved reports are immutable

## Security

- PER generation requires Regulatory Author role
- PER approval requires Regulatory Approver role
- PER content is reproducible from baseline for audit verification
- Report generation shall not bypass Product, Claim, Evidence, Performance or Risk approval decisions; it consumes their frozen outputs

## AI Support

- AI may draft PER sections from structured data (draft only)
- AI may propose literature summaries for scientific validity sections
- AI may identify evidence gaps for the completeness report
- AI-generated content is flagged in the output

## Acceptance Criteria

- A PER draft can be generated from approved product data.
- The canonical JSON-first PER draft can be generated from an existing frozen Performance Evaluation baseline without live regulatory-object payload reads.
- Generated PER includes traceability to exact frozen source object versions.
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

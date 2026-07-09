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

## Interfaces

- Product Service — product metadata and intended purpose
- Claim Service — claim data
- Evidence Service — evidence links and quality ratings
- Performance Service — study data and results
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

## Workflow

- PER lifecycle: data collection → draft generation → review → approval → publication
- Report regeneration triggers version bump
- Approved reports are immutable

## Security

- PER generation requires Regulatory Author role
- PER approval requires Regulatory Approver role
- PER content is reproducible from baseline for audit verification

## AI Support

- AI may draft PER sections from structured data (draft only)
- AI may propose literature summaries for scientific validity sections
- AI may identify evidence gaps for the completeness report
- AI-generated content is flagged in the output

## Acceptance Criteria

- A PER draft can be generated from approved product data.
- Generated PER includes traceability to source objects.
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

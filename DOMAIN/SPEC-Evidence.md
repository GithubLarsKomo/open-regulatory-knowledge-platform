# SPEC-Evidence.md

## Purpose

Define the evidence management domain that supports linking scientific and technical evidence to claims, risks and performance data.

## Scope

The domain covers:

- Evidence items and their metadata
- Evidence types (literature, study data, clinical data, performance data, historical data)
- Evidence lifecycle and quality assessment
- Evidence-to-claim linking
- Evidence-to-risk-control linking
- Evidence coverage analysis

## Stakeholders

- Regulatory Affairs
- Clinical Evidence Reviewer
- R&D
- Quality Management

## Domain Model

An Evidence Item is a structured reference to a source of information that supports or contradicts a regulatory statement.

Evidence Items may be associated with:

- Claims (supporting evidence)
- Risk Controls (verification evidence)
- Performance Studies (source data)
- Literature references
- PMS/PMPF data

### Evidence Types

- Literature Reference — a published study, article or standard
- Clinical Data — clinical study results
- Analytical Data — analytical performance study results
- Scientific Validity — scientific validity data
- Historical Data — post-market or legacy data
- Standards Reference — applicable standard or guideline
- Internal Report — verified internal study

## Requirements

### REQ-EVID-0001
The system shall store evidence items as structured objects with type, title, source reference and lifecycle state.

### REQ-EVID-0002
Each evidence item shall include metadata: author, publication date, journal or source, version and quality assessment.

### REQ-EVID-0003
Evidence items shall be linkable to claims, risk controls and performance studies.

### REQ-EVID-0004
The system shall support quality rating of evidence items (high, medium, low).

### REQ-EVID-0005
The system shall identify claims or risk controls lacking sufficient evidence coverage.

### REQ-EVID-0006
Literature evidence shall store PMID, DOI or other persistent identifiers where available.

### REQ-EVID-0007
Evidence items shall be versionable and auditable.

### REQ-EVID-0008
External attachments (PDF, data files) shall be stored with checksum and version reference.

## Interfaces

- Claim Service — evidence retrieval for claim substantiation
- Risk Service — evidence retrieval for risk control verification
- Performance Service — evidence linking for study results
- Report Service — evidence citations in generated reports
- AI Service — evidence retrieval for grounded drafting

## Data Model

### evidence_item

| Field | Type | Description |
|---|---|---|
| evidence_uuid | UUID | Stable identifier |
| evidence_type | VARCHAR | Evidence type code |
| title | VARCHAR | Title of evidence |
| source_reference | VARCHAR | PMID, DOI, URL or internal ref |
| author | VARCHAR | Author or organization |
| publication_date | DATE | Publication or issue date |
| journal | VARCHAR | Journal or source name |
| version | VARCHAR | Version identifier |
| quality_rating | VARCHAR | high/medium/low |
| quality_notes | TEXT | Assessment notes |
| checksum | VARCHAR | SHA-256 of attached file |
| lifecycle_state | VARCHAR | Lifecycle state |
| owner_user_id | VARCHAR | Responsible person |
| created_at | DATETIME | Creation timestamp |
| updated_at | DATETIME | Last update timestamp |

## Workflow

- Evidence lifecycle: draft → in_review → approved → superseded
- Quality assessment performed by Clinical Evidence Reviewer role
- Superseded evidence retains links but is flagged

## Security

- Evidence items visible per product-level permissions
- Quality assessment requires Clinical Evidence Reviewer role

## AI Support

- AI may propose evidence summaries (draft only)
- AI may suggest relevant literature from external databases
- AI shall not assign quality ratings without human review

## Acceptance Criteria

- An evidence item can be created with type and source reference.
- A claim can be linked to one or more evidence items.
- Coverage gaps (claims without evidence) can be detected.
- Evidence items appear in report citation sections.

## Open Questions

- Should evidence quality assessment follow a formal scoring rubric?
- How to handle confidential evidence (trade secrets, unpublished data)?
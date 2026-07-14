# SPEC-Evidence.md

## Purpose

Define the evidence management domain that supports linking scientific and technical evidence to claims, risks and performance data.

## Scope

The domain covers:

- Evidence items and their structured metadata
- Evidence types: literature, clinical study, analytical study, scientific validity, internal report, external report, standard, guideline, regulation
- Evidence lifecycle and quality assessment
- Evidence-to-claim linking
- Evidence-to-risk-control linking
- Evidence coverage analysis
- Evidence supersession and versioning

## Stakeholders

- Regulatory Affairs — define evidence strategy
- Clinical Evidence Reviewer — assess evidence quality
- R&D — contribute study data
- Quality Management — review evidence quality
- Notified Body — review evidence during submission

## Architecture

Evidence items are stored as `RegulatoryObject` with `object_type='evidence'`.
The payload schema is defined in `EvidencePayload` (Pydantic, `extra='forbid'`).

Evidence is linked to claims via `ObjectRelation` with types `supported_by` or `contradicted_by`.

```text
Evidence --supported_by--> Claim
Evidence --mitigates--> RiskControl
```

## Lifecycle

```text
draft -> in_review -> approved -> superseded
    ^         |
    +-- rejected
```

## Workflow

1. Author creates an evidence item with type, title and source reference.
2. Clinical Evidence Reviewer performs quality assessment.
3. Evidence is approved or rejected.
4. Approved evidence can be linked to claims.
5. Superseded evidence retains all links but is flagged as superseded.

## Evidence Types

- Literature — published article, study or review
- Clinical Study — clinical performance study data
- Analytical Study — analytical performance study data
- Scientific Validity — scientific validity data
- Internal Validation — internal verification report
- External Validation — external validation report
- Reference Standard — reference material or standard
- Regulatory Guidance — regulatory guidance document
- Standards — applicable standard or guideline
- Internal Document — internal technical document

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

### REQ-EVID-0009
Evidence shall support multiple types: literature, clinical_study, analytical_study, scientific_validity, internal_report, external_report, standard, guideline, regulation.

### REQ-EVID-0010
Each evidence item shall have an evidence category for grouping and reporting purposes.

### REQ-EVID-0011
Evidence shall support supersession where a newer version replaces an older one while retaining historical links.

### REQ-EVID-0012
Evidence quality shall include a structured assessment with criteria and reviewer comments.

### REQ-EVID-0013
The system shall track which claims reference each evidence item and report impact when evidence is superseded.

### REQ-EVID-0014
Evidence items shall support keyword and full-text search where applicable.

### REQ-EVID-0015
Evidence linked to approved claims shall not be deleted without impact assessment.

### REQ-EVID-0016
Evidence coverage shall be evaluated per product, per claim and per risk.

### REQ-EVID-0017
Evidence metadata shall include publication status (published, preprint, unpublished, confidential).

### REQ-EVID-0018
AI may propose evidence summaries and relevance scoring but shall not assign quality ratings.

### REQ-EVID-0019
Evidence items may reference external databases (PubMed, ClinicalTrials.gov, regulatory databases) via persistent identifiers.

### REQ-EVID-0020
Evidence-to-claim links shall reference explicit evidence and claim versions for traceability.

## Interfaces

- Claim Service — evidence retrieval for claim substantiation
- Risk Service — evidence retrieval for risk control verification
- Performance Service — evidence linking for study results
- Report Service — evidence citations in generated reports
- AI Service — evidence retrieval for grounded drafting

## Data Model

### EvidencePayload (Pydantic, extra='forbid')

| Field | Type | Required | Description |
|---|---|---|---|
| evidence_type | str | Yes | literature, clinical_study, analytical_study, scientific_validity, internal_report, external_report, standard, guideline, regulation |
| title | str | Yes | Title of evidence |
| source_reference | str | No | PMID, DOI, URL or internal ref |
| author | str | No | Author or organization |
| publication_date | str | No | Publication or issue date |
| journal | str | No | Journal or source name |
| version | str | No | Version identifier |
| quality_rating | str | No | high, medium, low |
| quality_notes | str | No | Assessment notes |
| evidence_category | str | No | Grouping category |
| publication_status | str | No | published, preprint, unpublished, confidential |
| keywords | List[str] | No | Search keywords |
| checksum | str | No | SHA-256 of attached file |

## Acceptance Criteria

- An evidence item can be created with type and source reference.
- A claim can be linked to one or more evidence items via ObjectRelation.
- Coverage gaps (claims without evidence) can be detected.
- Evidence items can be superseded while retaining historical links.
- Evidence items appear in report citation sections.
- Unknown payload fields are rejected.

## Open Questions

- Should evidence quality assessment follow a formal scoring rubric?
- How to handle confidential evidence (trade secrets, unpublished data)?
- Should the system integrate with external reference databases?
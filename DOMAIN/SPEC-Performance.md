# SPEC-Performance.md

## Purpose

Define analytical and clinical performance evidence management.

## Stakeholders

- Regulatory Affairs
- Clinical Evidence Reviewer
- R&D
- Quality Management

## Domain Model

### Core Entities

- Performance Study — a structured investigation of analytical or clinical performance, or scientific validity; persisted as `RegulatoryObject` with `object_type='study'`
- Study Result — measured outcomes from a performance study
- Scientific Validity Statement — documented scientific validity
- Evidence Link — connection to supporting evidence item

### PerformanceStudyPayload

- `study_id`: stable study identifier
- `study_type`: `analytical`, `clinical`, or `scientific_validity`
- `title`: human-readable study title
- `description`: optional study description
- `product`: exact version-pinned Product reference
- `study_status`: `planned`, `ongoing`, `completed`, or `archived`
- `owner_user_id`: responsible user

A new Performance Study must reference the exact current Product version. Persisted historical Study versions remain readable even when the Product is later versioned.

## Scope

The domain covers:

- Scientific validity
- Analytical performance
- Clinical performance
- Performance studies
- Literature evidence
- Statistical outputs
- PER generation

## Requirements

### REQ-PERF-0001
The system shall store performance studies as structured objects.

### REQ-PERF-0002
The system shall distinguish analytical performance, clinical performance and scientific validity.

### REQ-PERF-0003
Performance results shall be linked to claims.

### REQ-PERF-0004
Statistical outputs shall be traceable to source data or validated study reports.

### REQ-PERF-0005
The system shall support generation of Performance Evaluation Report sections.

### REQ-PERF-0006
The system shall identify performance claims lacking sufficient evidence.

## Acceptance Criteria

- A performance study can be registered as a strict `study` object for an exact current Product version.
- Analytical performance, clinical performance and scientific validity are represented as distinct validated study types.
- Results can be linked to claims.
- Evidence coverage can be calculated.
- PER sections can be generated from approved evidence.

## Interfaces

- Product Service — retrieves and validates exact Product context for studies
- Claim Service — links performance results to claims
- Evidence Service — stores and retrieves evidence for study support
- Risk Service — provides risk-benefit data for PER
- Report Service — generates PER sections from study data
- AI Service — evidence summarization and gap analysis
- REST API — creates Product-scoped Performance Studies and retrieves exact Study versions

## Data Model

### performance_study

| Field | Type | Description |
|---|---|---|
| study_uuid | UUID | Stable object UUID |
| study_id | VARCHAR | Stable domain identifier |
| study_type | VARCHAR | analytical/clinical/scientific_validity |
| title | VARCHAR | Study title |
| description | TEXT | Study description |
| product | VersionedObjectReference | Exact Product UUID and object-store version |
| study_status | VARCHAR | planned/ongoing/completed/archived |
| lifecycle_state | VARCHAR | Regulatory object lifecycle state |
| owner_user_id | VARCHAR | Responsible person |
| created_at | DATETIME | Object creation timestamp |
| updated_at | DATETIME | Object update timestamp |

### study_result

| Field | Type | Description |
|---|---|---|
| result_uuid | UUID | Stable identifier |
| study_uuid | UUID | Linked study |
| parameter | VARCHAR | Measured parameter |
| result_value | TEXT | Result value |
| statistical_method | VARCHAR | Statistical method used |
| source_data_ref | VARCHAR | Reference to source data |

Study Result persistence and graph relations are introduced in the `REQ-PERF-0003`/`REQ-PERF-0004` slices rather than being folded into the Study core.

## Workflow

- Study creation: exact current Product → strict Performance Study draft
- Study lifecycle: draft → in_review → approved → effective → superseded
- Historical Study versions retain their exact Product reference
- Results linked to claims before approval
- Evidence coverage analysis run before PER generation

## Security

- Study creation requires Regulatory Author or R&D Contributor role
- Study approval requires Clinical Evidence Reviewer role
- Results visible per product-level permissions

## AI Support

- AI may summarize study results (draft only)
- AI may identify claims lacking sufficient evidence (REQ-PERF-0006)
- AI may propose evidence coverage reports
- AI shall not approve study results or conclusions

## Open Questions

- How to model multi-center studies vs. single-center studies?
- Should study protocols be versioned as separate objects?
- How to handle literature-based vs. lab-generated evidence?

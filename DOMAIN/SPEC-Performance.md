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
- Performance Result — structured Evidence derived from an exact Performance Study version and linked to one or more exact Claim versions
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

### PerformanceResultPayload

- persisted as Core `RegulatoryObject` with `object_type='evidence'`
- `result_id`: stable result identifier
- `study`: exact version-pinned Performance Study reference
- `claims`: one or more exact version-pinned Claim references
- `parameter`: measured performance parameter
- `result_value`: structured textual value
- optional `unit`, `statistical_method`, and `interpretation`
- `quality_rating`: `high`, `medium`, or `low`
- `owner_user_id`: responsible user
- `evidence_type`: server-derived from the source Study category

The canonical graph is:

```
Evidence(PerformanceResult) --derived_from(role=performance_result_source)--> Study
Evidence(PerformanceResult) --supported_by--> Claim
```

The server derives `evidence_type` as `analytical_study`, `clinical_study`, or `scientific_validity` from the Study type. This keeps Performance Results compatible with the existing Claim Evidence Policy and avoids a parallel result/evidence model.

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
- Performance Results are persisted as strict Evidence objects derived from exact Study versions.
- Performance Results support one or more exact Claim versions through canonical `supported_by` relations.
- Evidence coverage can be calculated.
- PER sections can be generated from approved evidence.

## Interfaces

- Product Service — retrieves and validates exact Product context for studies
- Claim Service — consumes Performance Results through existing Evidence relations and approval assessment
- Evidence Service — exposes Performance Results through the standard Evidence graph
- Risk Service — provides risk-benefit data for PER
- Report Service — generates PER sections from study data
- AI Service — evidence summarization and gap analysis
- REST API — creates Product-scoped Performance Studies, creates Study-scoped Performance Results, and retrieves exact versions

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

### performance_result_evidence

| Field | Type | Description |
|---|---|---|
| result_uuid | UUID | Evidence object UUID |
| result_id | VARCHAR | Stable Performance Result identifier |
| study | VersionedObjectReference | Exact source Study version |
| claims | List[VersionedObjectReference] | Exact supported Claim versions |
| parameter | VARCHAR | Measured parameter |
| result_value | TEXT | Result value |
| unit | VARCHAR | Optional unit |
| statistical_method | VARCHAR | Optional statistical method |
| interpretation | TEXT | Optional interpretation |
| quality_rating | VARCHAR | high/medium/low |
| evidence_type | VARCHAR | Derived evidence classification |

Raw source-data / validated-report provenance for statistical outputs is added separately under `REQ-PERF-0004`.

## Workflow

- Study creation: exact current Product → strict Performance Study draft
- Study lifecycle: draft → in_review → approved → effective → superseded
- Historical Study versions retain their exact Product reference
- Current Study + current Claim version(s) → Performance Result Evidence → version-pinned Study provenance + Claim support
- Historical Performance Results remain readable after later Study/Claim versions
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

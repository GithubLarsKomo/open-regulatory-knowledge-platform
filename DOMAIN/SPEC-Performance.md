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

- Performance Study — a structured investigation of analytical or clinical performance
- Study Result — measured outcomes from a performance study
- Scientific Validity Statement — documented scientific validity
- Evidence Link — connection to supporting evidence item

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

- A performance study can be registered.
- Results can be linked to claims.
- Evidence coverage can be calculated.
- PER sections can be generated from approved evidence.

## Interfaces

- Product Service — retrieves product context for studies
- Claim Service — links performance results to claims
- Evidence Service — stores and retrieves evidence for study support
- Risk Service — provides risk-benefit data for PER
- Report Service — generates PER sections from study data
- AI Service — evidence summarization and gap analysis

## Data Model

### performance_study

| Field | Type | Description |
|---|---|---|
| study_uuid | UUID | Stable identifier |
| study_type | VARCHAR | analytical/clinical/scientific_validity |
| title | VARCHAR | Study title |
| description | TEXT | Study description |
| product_uuid | UUID | Linked product |
| study_status | VARCHAR | planned/ongoing/completed/archived |
| lifecycle_state | VARCHAR | Lifecycle state |
| owner_user_id | VARCHAR | Responsible person |
| created_at | DATETIME | Creation timestamp |
| updated_at | DATETIME | Last update timestamp |

### study_result

| Field | Type | Description |
|---|---|---|
| result_uuid | UUID | Stable identifier |
| study_uuid | UUID | Linked study |
| parameter | VARCHAR | Measured parameter |
| result_value | TEXT | Result value |
| statistical_method | VARCHAR | Statistical method used |
| source_data_ref | VARCHAR | Reference to source data |

## Workflow

- Study lifecycle: draft → in_review → approved → effective → superseded
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

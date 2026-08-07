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
- Performance Evaluation Baseline — frozen Product, Performance Result and exact provenance snapshots used to generate reproducible PER sections
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
- `statistical_sources`: exact source Evidence references used when a statistical method is present
- `quality_rating`: `high`, `medium`, or `low`
- `owner_user_id`: responsible user
- `evidence_type`: server-derived from the source Study category

The canonical graph is:

```
Evidence(PerformanceResult) --derived_from(role=performance_result_source)--> Study
Evidence(PerformanceResult) --supported_by--> Claim
Evidence(PerformanceResult) --derived_from(role=statistical_source_data)--> Evidence(internal_document)
Evidence(PerformanceResult) --derived_from(role=validated_study_report)--> Evidence(internal_report|external_report)
```

The server derives `evidence_type` as `analytical_study`, `clinical_study`, or `scientific_validity` from the Study type. This keeps Performance Results compatible with the existing Claim Evidence Policy and avoids a parallel result/evidence model.

### PerformanceStatisticalSource

- `source_kind`: `source_data` or `validated_report`
- `evidence`: exact version-pinned Evidence reference
- `source_data` must reference current `internal_document` Evidence
- `validated_report` must reference current `internal_report` or `external_report` Evidence whose object lifecycle is `approved` or `effective` and whose exact ObjectVersion is approved
- duplicate exact Evidence references are not permitted
- a Performance Result with `statistical_method` requires at least one statistical source

Statistical provenance is captured both in the strict Performance Result payload and in exact version-pinned `derived_from` relations. Later source Evidence versions do not rewrite the historical Result provenance.

### Performance Evaluation Baseline and PER Sections

A Performance Evaluation baseline freezes one exact current approved/effective Product version and one or more exact current approved/effective Performance Result Evidence versions. Each selected Performance Result Evidence version must itself be approved.

For each selected Performance Result, the baseline transitively freezes the exact Study, Claim and statistical-source versions referenced by the Result payload. Referenced Claims must be current approved/effective versions and their exact ObjectVersions must be approved. Historical Study and statistical-source versions referenced by approved Results are preserved rather than silently upgraded.

The baseline rejects conflicting versions of the same object. After freeze, PER generation reads only `Baseline` and `BaselineItem.snapshot_json`; live RegulatoryObject/ObjectVersion payloads are not consulted.

Canonical deterministic JSON groups Performance Results into:

- `scientific_validity`
- `analytical_performance`
- `clinical_performance`

Each section item contains the exact frozen Performance Result, Study, Claim and statistical-source snapshots. Canonical JSON is SHA-256 hashed and persisted as a `GeneratedArtifact` with `artifact_type='performance_evaluation_sections'` plus an `artifact_generated` audit event. PDF/DOCX rendering is deferred to the Report Generation capability.

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
- Statistical Performance Results require exact current source-data or validated-report Evidence provenance.
- Validated report provenance requires approved/effective report Evidence and an approved exact Evidence version.
- A PER baseline freezes an approved/effective Product, approved/effective Performance Results, current approved Claims and exact Study/statistical-source provenance.
- PER section generation is deterministic and reads only frozen baseline snapshots.
- Repeated generation from the same baseline produces identical canonical JSON and checksum.
- Evidence coverage can be calculated.
- PER sections can be generated from approved evidence.

## Interfaces

- Product Service — retrieves and validates exact Product context for studies and PER baselines
- Claim Service — consumes Performance Results through existing Evidence relations and approval assessment
- Evidence Service — exposes Performance Results and statistical source provenance through the standard Evidence graph
- Risk Service — provides risk-benefit data for PER
- Performance Report Service — freezes exact Performance context and generates reproducible PER section manifests
- Report Service — renders approved/frozen manifests into final document formats
- AI Service — evidence summarization and gap analysis
- REST API — creates Product-scoped Performance Studies, Study-scoped Performance Results and Performance Report baselines; retrieves exact versions and generates deterministic PER sections

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
| statistical_sources | List[PerformanceStatisticalSource] | Exact statistical provenance; required when statistical_method is set |
| interpretation | TEXT | Optional interpretation |
| quality_rating | VARCHAR | high/medium/low |
| evidence_type | VARCHAR | Derived evidence classification |

### performance_evaluation_baseline

| Field | Type | Description |
|---|---|---|
| baseline_uuid | UUID | Frozen baseline identifier |
| product | VersionedObjectReference | Exact approved/effective current Product version |
| evidence | List[VersionedObjectReference] | Selected approved/effective Performance Result versions |
| transitive_items | BaselineItem[] | Exact Study, Claim and statistical-source snapshots derived from selected Results |
| checksum | SHA-256 | Deterministic checksum of generated canonical PER section JSON |

## Workflow

- Study creation: exact current Product → strict Performance Study draft
- Study lifecycle: draft → in_review → approved → effective → superseded
- Historical Study versions retain their exact Product reference
- Current Study + current Claim version(s) → Performance Result Evidence → version-pinned Study provenance + Claim support
- Statistical method → mandatory exact source-data or validated-report Evidence provenance
- Historical Performance Results retain their original source Evidence versions even after those sources are versioned later
- Approved/effective Product + approved/effective Performance Results + current approved Claims → frozen Performance Evaluation baseline
- Frozen baseline snapshots → deterministic scientific-validity / analytical-performance / clinical-performance section JSON → checksum + GeneratedArtifact
- Evidence coverage analysis run before PER generation

## Security

- Study creation requires Regulatory Author or R&D Contributor role
- Study approval requires Clinical Evidence Reviewer role
- Results visible per product-level permissions
- Validated-report provenance can only reference approved/effective report Evidence
- PER baseline generation accepts only approved/effective Product, Performance Result and Claim decision context

## AI Support

- AI may summarize study results (draft only)
- AI may identify claims lacking sufficient evidence (REQ-PERF-0006)
- AI may propose evidence coverage reports
- AI shall not approve study results, claim sufficiency or conclusions

## Open Questions

- How to model multi-center studies vs. single-center studies?
- Should study protocols be versioned as separate objects?
- How to handle literature-based vs. lab-generated evidence?

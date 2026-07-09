# TASK.md
# Initial SWE Batch Plan

## Epic 001 — Specification Foundation

### TASK-FOUNDATION-0001
Create repository skeleton.

Source requirements:

- REQ-CORE-0001
- REQ-ARCH-0001

Acceptance criteria:

- Folder structure exists.
- Root SPEC.md exists.
- META rules exist.
- Initial DOMAIN, DATABASE, GRAPH, AI and REPORTS files exist.

### TASK-FOUNDATION-0002
Implement specification ID linter.

Source requirements:

- META-ID-0001
- META-TASK-0001

Acceptance criteria:

- Script scans Markdown files.
- Script detects duplicate IDs.
- Script reports obsolete IDs.
- Script outputs traceability CSV.

### TASK-FOUNDATION-0003
Generate initial task backlog from SPEC files.

Acceptance criteria:

- Requirements are parsed from Markdown.
- Tasks can reference requirement IDs.
- Output is Markdown and CSV.

## Epic 002 — Core Object Store

### TASK-CORE-0001
Create MariaDB schema for regulatory_object and object_version.

Source requirements:

- DB-CORE-0001
- DB-CORE-0002
- DB-CORE-0005

Acceptance criteria:

- DDL migration exists.
- Unit test inserts draft object.
- Unit test creates version.
- Approved version cannot be modified.

### TASK-CORE-0002
Create REST endpoint for regulatory object retrieval.

Source requirements:

- API-REST-0001
- API-REST-0004

Acceptance criteria:

- GET object by UUID.
- GET object version history.
- Unauthorized access rejected.

## Epic 003 — Event Store & Audit Trail

### TASK-EVENT-0001
Create event store schema and append-only event log.

Source requirements:

- REQ-ARCH-0004
- DB-CORE-0003

Acceptance criteria:

- Event log table exists.
- Event append preserves history.
- Events can be replayed for object reconstruction.

### TASK-EVENT-0002
Create audit trail REST endpoints.

Source requirements:

- SEC-RBAC-0005
- API-REST-0001

Acceptance criteria:

- GET audit log by object UUID.
- GET audit log filtered by user, date range.
- Audit log read-only for non-admin roles.

## Epic 004 — Product & Claim Domain

### TASK-PROD-0001
Create Product domain schema and CRUD endpoints.

Source requirements:

- REQ-PROD-0001
- REQ-PROD-0002
- REQ-PROD-0003
- REQ-PROD-0004
- REQ-PROD-0007

Acceptance criteria:

- Product can be created with regulatory identifiers.
- Device variants can be added to product.
- Product lifecycle state transitions work.

### TASK-CLAIM-0001
Create Claim domain schema and CRUD endpoints.

Source requirements:

- REQ-CLAIM-0001
- REQ-CLAIM-0002
- REQ-CLAIM-0003
- REQ-CLAIM-0004

Acceptance criteria:

- Claim can be created with type, jurisdiction, language.
- Evidence can be linked to a claim.
- Approved claims are reusable across reports.

### TASK-CLAIM-0002
Implement claim consistency checking and approval workflow.

Source requirements:

- REQ-CLAIM-0005
- REQ-CLAIM-0006
- WF-APP-0001

Acceptance criteria:

- System detects inconsistent claim wording across artifacts.
- Claim cannot be approved without evidence or justification.
- Approval follows lifecycle state machine.

## Epic 005 — Risk Domain

### TASK-RISK-0001
Create Risk domain schema and CRUD endpoints.

Source requirements:

- REQ-RISK-0001
- REQ-RISK-0002
- REQ-RISK-0003

Acceptance criteria:

- Hazard, hazardous situation and harm can be created.
- Risk controls can be linked to risks.
- Verification evidence can be linked to controls.

### TASK-RISK-0002
Implement risk approval, residual risk evaluation and report generation.

Source requirements:

- REQ-RISK-0004
- REQ-RISK-0005
- REQ-RISK-0006

Acceptance criteria:

- Residual risk requires documented evaluation.
- Risk traceability to requirements and claims visible.
- Risk Management Report section can be generated.

## Epic 006 — Performance Domain

### TASK-PERF-0001
Create Performance domain schema and study registration.

Source requirements:

- REQ-PERF-0001
- REQ-PERF-0002
- REQ-PERF-0004

Acceptance criteria:

- Performance study can be registered with type.
- Study results can be stored with statistical metadata.
- Results traceable to source data.

### TASK-PERF-0002
Implement evidence coverage analysis and PER section generation.

Source requirements:

- REQ-PERF-0003
- REQ-PERF-0005
- REQ-PERF-0006

Acceptance criteria:

- Performance results linkable to claims.
- Evidence coverage can be calculated.
- PER sections can be generated from approved evidence.

## Epic 007 — Report Generation MVP

### TASK-REPORT-0001
Create report generation engine for DOCX and PDF output.

Source requirements:

- REQ-CORE-0002
- REQ-CORE-0007
- REP-PER-0001
- REP-PER-0005

Acceptance criteria:

- Report can be generated from structured data and template.
- Output is reproducible from baseline.
- DOCX and PDF formats supported.

### TASK-REPORT-0002
Implement PER generation with traceability and completeness report.

Source requirements:

- REP-PER-0002
- REP-PER-0003
- REP-PER-0004

Acceptance criteria:

- PER includes traceability to source objects.
- Approved text distinguished from AI-generated draft.
- Completeness report lists missing evidence.

## Epic 008 — Knowledge Graph

### TASK-GRAPH-0001
Create Neo4j schema and data synchronization from object store.

Source requirements:

- GRAPH-CORE-0001
- GRAPH-CORE-0003

Acceptance criteria:

- Neo4j node types created matching object types.
- Edge types created matching relationships.
- Data synchronized from MariaDB object store.

### TASK-GRAPH-0002
Implement traceability queries and impact analysis.

Source requirements:

- GRAPH-CORE-0002
- GRAPH-CORE-0004

Acceptance criteria:

- Traceability path query works (Claim → Evidence → Study).
- Impact analysis shows affected objects on change.
- Graph not used as primary approval record.

## Epic 009 — AI/RAG Services

### TASK-AI-0001
Create hybrid search service (keyword, vector, graph).

Source requirements:

- AI-CORE-0005

Acceptance criteria:

- Keyword search returns relevant objects.
- Vector search returns semantically similar objects.
- Graph traversal returns relationship-based results.

### TASK-AI-0002
Implement grounded drafting with source citation.

Source requirements:

- AI-CORE-0001
- AI-CORE-0002
- AI-CORE-0003

Acceptance criteria:

- AI can generate draft text from retrieved evidence.
- Generated text cites source objects.
- Distinction between facts, inferences and generated wording visible.

### TASK-AI-0003
Implement AI audit trail and evidence gap analysis.

Source requirements:

- AI-CORE-0004
- REQ-CORE-0006
- WF-APP-0006

Acceptance criteria:

- Prompts, context references and draft versions stored.
- AI-generated content requires human review before approval.
- Evidence gaps identified and reported.

## Epic 010 — Workflow & Security

### TASK-WF-0001
Implement object lifecycle state machine and approval workflow.

Source requirements:

- WF-APP-0001
- WF-APP-0002
- WF-APP-0003
- WF-APP-0004

Acceptance criteria:

- Objects transition through defined lifecycle states.
- Approval requires identified approver + timestamp + decision.
- Rejected objects retain reviewer comments.
- Approved versions immutable.

### TASK-WF-0002
Implement electronic signatures and RBAC enforcement.

Source requirements:

- WF-APP-0005
- SEC-RBAC-0001
- SEC-RBAC-0002
- SEC-RBAC-0003
- SEC-RBAC-0004

Acceptance criteria:

- Electronic signatures supported.
- Role-based access enforced per object type.
- Product-specific permissions work.
- Read-only audit access available.
- Approval permissions separated from authoring permissions.

## Epic 011 — UI

### TASK-UI-0001
Create dashboard, search and object browsing views.

Source requirements:

- REQ-UI-0001
- REQ-UI-0002
- REQ-UI-0003
- REQ-UI-0009
- REQ-UI-0010

Acceptance criteria:

- Dashboard shows task summaries, pending approvals.
- Search supports faceted filters.
- Object detail view shows version history and relationships.
- Responsive and accessible (WCAG 2.1 AA).

### TASK-UI-0002
Create editing, workflow, AI drafting and report generation interfaces.

Source requirements:

- REQ-UI-0004
- REQ-UI-0005
- REQ-UI-0006
- REQ-UI-0007
- REQ-UI-0008

Acceptance criteria:

- Structured forms for draft creation and editing.
- Traceability graph visualization.
- Review/approve/reject workflow UI.
- AI drafting panel with source citations.
- Report generation with template selection.

## Epic 012 — Validation & Deployment

### TASK-VAL-0001
Create validation plan and requirement-to-test traceability.

Source requirements:

- TEST-VAL-0001
- TEST-VAL-0002

Acceptance criteria:

- Validation plan document exists.
- Each requirement linked to one or more test cases.

### TASK-VAL-0002
Verify report generation, audit trail and AI functions.

Source requirements:

- TEST-VAL-0003
- TEST-VAL-0004
- TEST-VAL-0005

Acceptance criteria:

- Report generation verified against known baselines.
- Audit trail integrity tested.
- AI functions validated for intended use limitations.

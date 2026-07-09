# SPEC-UI.md

## Purpose

Define the web user interface for the Open Regulatory Knowledge Platform.

## Scope

The UI covers:

- Dashboard and navigation
- Object browsing and search
- Object detail and editing views
- Relationship visualization
- Workflow and approval interfaces
- Report generation interface
- AI-assisted drafting interface
- Administration and user management

## Stakeholders

- Regulatory Authors
- QM Reviewers
- Regulatory Approvers
- R&D Contributors
- Clinical Evidence Reviewers
- Auditors
- System Administrators

## Requirements

### REQ-UI-0001
The UI shall provide a dashboard showing task summaries, pending approvals, evidence gaps and recent activity.

### REQ-UI-0002
The UI shall support browsing and searching all regulatory object types with faceted filters.

### REQ-UI-0003
The UI shall display object details with version history, lifecycle state and linked relationships.

### REQ-UI-0004
The UI shall support creating and editing draft objects through structured forms.

### REQ-UI-0005
The UI shall visualize traceability relationships as interactive graphs.

### REQ-UI-0006
The UI shall provide workflow interfaces for review, approval and rejection with comment input.

### REQ-UI-0007
The UI shall provide an AI drafting interface that shows source citations and distinguishes draft from approved content.

### REQ-UI-0008
The UI shall support report generation with template selection, baseline configuration and download.

### REQ-UI-0009
The UI shall be responsive and accessible (WCAG 2.1 AA).

### REQ-UI-0010
The UI shall support user authentication, role-based views and product-scoped navigation.

## Interfaces

- REST API (API-REST-0001) — all data access through API layer
- Knowledge Graph API — relationship visualization
- AI Service — drafting and evidence summarization

## Data Model

No separate data model — the UI renders data from the REST API layer.

## Workflow

- Object lifecycle operations initiated from UI views
- Approval actions (submit, approve, reject, return_to_draft) via dedicated UI
- Confirmation dialogs for irreversible actions (approve, reject)

## Security

- UI enforces role-based views per SEC-RBAC-0001
- UI hides objects and actions not permitted per user permissions
- Session management with configurable timeout

## AI Support

- AI drafting panel with source citations
- AI consistency check results displayed inline
- AI confidence indicators shown alongside suggestions

## Acceptance Criteria

- A user can log in and see a role-appropriate dashboard.
- A user can search for objects and view details.
- A user can create a draft and submit for review.
- A reviewer can approve or reject with comment.
- Relationships are visible in graph view.
- A report can be generated and downloaded.

## Open Questions

- Single-page application (React/Vue) vs server-rendered UI?
- Should graph visualization use a specific library (e.g., vis.js, D3.js, Cytoscape.js)?
- Mobile support priority?
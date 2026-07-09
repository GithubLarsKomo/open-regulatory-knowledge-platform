# SPEC-REST.md

## Purpose

Define REST API principles.

## Scope

The REST API layer covers:

- CRUD operations for all regulatory object types
- Object version history access
- Search and query endpoints
- Report generation triggers
- Workflow actions (submit, approve, reject)
- AI drafting requests
- Baseline management

## Stakeholders

- Regulatory Authors — create and edit objects via API
- QM Reviewers — review and approve via API
- System Integrators — connect external systems
- UI Developers — consume API for frontend

## Requirements

### API-REST-0001
All core regulatory objects shall be accessible through REST endpoints.

### API-REST-0002
APIs shall be versioned.

### API-REST-0003
APIs shall support pagination, filtering and sorting.

### API-REST-0004
APIs shall expose object version history.

### API-REST-0005
APIs shall not expose unauthorized objects.

## Domain Model

### API Resource

| Concept | Description |
|---|---|
| Resource | A regulatory object type exposed via REST |
| Endpoint | URL path pattern for a resource |
| Collection | List of resources with pagination |
| Version | API version prefix (e.g., /api/v1/) |

## Interfaces

- Web UI — consumes REST API
- External Systems — REST API for integration
- Domain Services — backend implementation layer
- IAM Service — authentication and authorization

## Data Model

### Standard Response Envelope

```json
{
  "data": { ... },
  "meta": {
    "page": 1,
    "page_size": 50,
    "total": 142
  },
  "error": null
}
```

## Workflow

- All writes require authentication
- Object lifecycle transitions follow workflow rules defined in SPEC-Approval.md
- Idempotent writes where applicable

## Security

- API access requires authentication (JWT or equivalent)
- Role-based access enforced per endpoint
- Rate limiting on write endpoints
- Audit logging on all state-changing operations

## AI Support

- AI drafting accessible through dedicated API endpoints
- AI context can be supplied via API parameters

## Acceptance Criteria

- All regulatory objects accessible via REST.
- Pagination and filtering work correctly.
- Unauthorized access is rejected with 401/403.
- Version history is exposed for each object.

## Open Questions

- Should GraphQL be offered alongside REST?
- What rate limits are appropriate per role?
- Should bulk operations be supported?

```text
GET    /api/v1/objects/{id}
POST   /api/v1/claims
GET    /api/v1/claims/{id}/evidence
POST   /api/v1/reports/per/generate
GET    /api/v1/baselines/{id}
```

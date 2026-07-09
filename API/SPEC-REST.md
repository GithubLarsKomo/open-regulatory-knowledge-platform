# SPEC-REST.md

## Purpose

Define REST API principles.

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

## Example Endpoints

```text
GET    /api/v1/objects/{id}
POST   /api/v1/claims
GET    /api/v1/claims/{id}/evidence
POST   /api/v1/reports/per/generate
GET    /api/v1/baselines/{id}
```

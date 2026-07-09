# SPEC-RBAC.md

## Purpose

Define role-based access control.

## Roles

- System Administrator
- Regulatory Author
- QM Reviewer
- Regulatory Approver
- R&D Contributor
- Clinical Evidence Reviewer
- Auditor
- Read-only User

## Scope

The RBAC model covers:

- Role definitions and permissions
- Object-type aware access control
- Product-specific permission scoping
- Read-only audit access
- Separation of duties (author vs. approver)
- Authentication and session management

## Stakeholders

- System Administrators — configure roles and permissions
- Regulatory Authors — create and edit objects within scope
- QM Reviewers — review and approve within scope
- Regulatory Approvers — final approval authority
- R&D Contributors — contribute technical data
- Clinical Evidence Reviewers — assess evidence quality
- Auditors — read-only access to all objects and audit logs
- Read-only Users — view published objects

## Requirements

### SEC-RBAC-0001
Access shall be role-based and object-type aware.

### SEC-RBAC-0002
The system shall support product-specific permissions.

### SEC-RBAC-0003
The system shall support read-only audit access.

### SEC-RBAC-0004
Approval permissions shall be separated from authoring permissions.

### SEC-RBAC-0005
All access-relevant events shall be auditable.

## Domain Model

### Role Definition

| Role | Permissions |
|---|---|
| System Administrator | Full system access, user management, role assignment |
| Regulatory Author | Create/edit objects, submit for review |
| QM Reviewer | Review objects, request changes, approve/reject |
| Regulatory Approver | Final approval of regulated objects |
| R&D Contributor | Create/edit technical data within scope |
| Clinical Evidence Reviewer | Assess and rate evidence quality |
| Auditor | Read-only access to all objects and audit logs |
| Read-only User | View published/approved objects |

## Interfaces

- REST API — authentication and permission enforcement
- Domain Services — role checks before state transitions
- Audit Service — access event logging
- UI — role-based view rendering

## Data Model

| Field | Type | Description |
|---|---|---|
| role_id | VARCHAR | Stable role identifier |
| role_name | VARCHAR | Human-readable role name |
| permissions | JSON | Permission definitions |
| product_scope | JSON | Scoped product UUIDs (if applicable) |

## Workflow

- User authentication at session start
- Permission check on every API call
- Product scope filter applied to query results
- Auditors cannot modify any objects

## AI Support

- AI cannot override or modify role assignments
- AI may suggest permission configurations for audit review

## Acceptance Criteria

- A user with Regulatory Author role can create draft objects.
- A user without approval permission cannot approve objects.
- An Auditor can read all objects but cannot modify them.
- Product-scoped users only see their assigned products.
- All access events are logged.

## Open Questions

- Should roles be configurable per object type?
- How to handle temporary role delegation?
- Should there be emergency access (break-glass) procedures?

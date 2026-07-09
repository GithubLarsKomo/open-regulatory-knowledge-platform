# SPEC-CoreObjectStore.md

## Purpose

Define the Phase 3 target backend MVP — the core object store schema and data access layer for the Open Regulatory Knowledge Platform.

## Scope

The core object store covers:

- `regulatory_object` table — all domain objects with stable UUID identifiers
- `object_version` table — immutable version history with JSON payload
- `object_relation` table — explicit versioned relationships between objects
- `event_log` table — append-only audit event stream
- `baseline` and `baseline_item` tables — reproducibility snapshots
- Immutable approved versions
- Optimistic locking for concurrent edits
- Lifecycle state machine (draft → in_review → approved → effective → obsolete)
- Soft deletion support

## Stakeholders

- Backend Developers — implement the data access layer
- Regulatory Affairs — require immutable audit trail
- QM Reviewers — require approved version immutability
- System Administrators — manage schema migrations

## Domain Model

### Core Entities

| Entity | Description |
|---|---|
| RegulatoryObject | Base entity for all domain objects |
| ObjectVersion | Immutable snapshot of object payload at a version |
| ObjectRelation | Directed, versioned relationship between two objects |
| EventLog | Append-only record of state-changing operations |
| ApprovalRecord | Workflow approval or rejection record |
| Baseline | A named, timestamped snapshot of object versions |
| BaselineItem | One object version within a baseline |

### Lifecycle States

```
draft → in_review → approved → effective → obsolete
                ↓
            rejected → draft
```

## Requirements

### DB-OBJ-0001
The system shall store all regulatory objects in a `regulatory_object` table with a UUID primary key, object type string, current version number, lifecycle state, owner reference and timestamps.

### DB-OBJ-0002
The system shall store object versions in an `object_version` table with a composite key of object UUID and version number, a JSON payload column, status, creation timestamp and creator reference.

### DB-OBJ-0003
The system shall enforce that once an object version is approved, its payload becomes immutable and no further updates to that version are permitted.

### DB-OBJ-0004
The system shall support optimistic locking on the `regulatory_object` table via a version number or timestamp to prevent concurrent overwrites.

### DB-OBJ-0005
The system shall store directed, versioned relationships between objects in an `object_relation` table with source UUID, source version, target UUID, target version and relation type.

### DB-OBJ-0006
The system shall maintain an append-only `event_log` table that records every state-changing operation with event type, event payload, actor identity and timestamp.

### DB-OBJ-0007
The system shall support lifecycle state transitions (draft, in_review, approved, effective, rejected, obsolete) and validate that transitions follow the defined state machine.

### DB-OBJ-0008
The system shall support soft deletion by setting the lifecycle state to 'deleted' rather than physically removing rows.

### DB-OBJ-0009
The system shall store baselines in a `baseline` table and baseline items in a `baseline_item` table, where each baseline item references an exact object UUID and version number.

### DB-OBJ-0010
The system shall use SQLAlchemy 2.0 ORM models with Pydantic v2 schemas for serialization and validation.

## Interfaces

- Repository Layer — CRUD operations for regulatory objects
- Domain Services — business logic layer above the repository
- Event Store — append-only event log consumed by audit service
- Graph Synchronizer — reads object store events to update Neo4j

## Data Model

### DDL Sketch

```sql
CREATE TABLE regulatory_object (
  object_uuid BINARY(16) NOT NULL,
  object_type VARCHAR(64) NOT NULL,
  current_version INT NOT NULL DEFAULT 1,
  lifecycle_state VARCHAR(32) NOT NULL DEFAULT 'draft',
  owner_user_id VARCHAR(128),
  lock_version INT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (object_uuid)
);

CREATE TABLE object_version (
  object_uuid BINARY(16) NOT NULL,
  version_no INT NOT NULL,
  payload_json JSON NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'draft',
  created_at DATETIME NOT NULL,
  created_by VARCHAR(128) NOT NULL,
  PRIMARY KEY (object_uuid, version_no)
);

CREATE TABLE object_relation (
  relation_uuid BINARY(16) NOT NULL,
  source_object_uuid BINARY(16) NOT NULL,
  source_version INT,
  target_object_uuid BINARY(16) NOT NULL,
  target_version INT,
  relation_type VARCHAR(64) NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (relation_uuid)
);

CREATE TABLE event_log (
  event_uuid BINARY(16) NOT NULL,
  object_uuid BINARY(16),
  event_type VARCHAR(64) NOT NULL,
  event_payload JSON,
  actor_user_id VARCHAR(128),
  created_at DATETIME NOT NULL,
  PRIMARY KEY (event_uuid),
  INDEX idx_event_object (object_uuid),
  INDEX idx_event_created (created_at)
);

CREATE TABLE approval_record (
  approval_uuid BINARY(16) NOT NULL,
  object_uuid BINARY(16) NOT NULL,
  version_no INT NOT NULL,
  action VARCHAR(32) NOT NULL,
  approver_user_id VARCHAR(128) NOT NULL,
  comments TEXT,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (approval_uuid)
);

CREATE TABLE baseline (
  baseline_uuid BINARY(16) NOT NULL,
  description VARCHAR(256),
  created_at DATETIME NOT NULL,
  created_by VARCHAR(128) NOT NULL,
  PRIMARY KEY (baseline_uuid)
);

CREATE TABLE baseline_item (
  baseline_uuid BINARY(16) NOT NULL,
  object_uuid BINARY(16) NOT NULL,
  version_no INT NOT NULL,
  PRIMARY KEY (baseline_uuid, object_uuid, version_no)
);
```

## Workflow

1. Object creation inserts a regulatory_object row and the first object_version row.
2. Updates create new object_version rows; the regulatory_object.current_version is incremented.
3. Approval transitions the lifecycle_state to 'approved' and the version status to 'approved'.
4. Approved versions cannot be updated or deleted.
5. All state changes write an event_log entry.
6. Baselines are captured before report generation to ensure reproducibility.

## Security

- Database access is restricted to the application service account.
- Event log is append-only; no UPDATE or DELETE operations are permitted on event_log.
- Approved versions are immutable at the database level (UPDATE blocked).
- Lock_version prevents lost updates in concurrent scenarios.

## Acceptance Criteria

- A draft object can be created, retrieved, updated, submitted, approved and rejected.
- An approved object version is immutable.
- The event log records every state change.
- Optimistic locking prevents concurrent overwrites.
- A baseline can be created and its items retrieved.
- Soft-deleted objects are excluded from default queries.

## Open Questions

- Should UUIDs be stored as BINARY(16) or CHAR(36)?
- Should JSON schema validation be applied to payload_json?
- What indexing strategy is needed for the event_log table at scale?
# SPEC-MariaDB.md

## Purpose

Define a MariaDB-compatible relational reference model.

## Core Tables

- regulatory_object
- object_version
- object_relation
- event_log
- approval_record
- generated_artifact
- baseline
- baseline_item

## Scope

The MariaDB schema covers:

- Core object store (regulatory_object, object_version)
- Object relationships and version references
- Event log for audit trail
- Approval records
- Generated artifact storage
- Baseline snapshots for report reproducibility

## Stakeholders

- Database Administrators — schema management and performance
- Developers — data access layer
- Regulatory Affairs — data integrity and audit
- System Administrators — backup and recovery

## Requirements

### DB-CORE-0001
Every domain object shall be stored with a stable UUID.

### DB-CORE-0002
Every object version shall be immutable after approval.

### DB-CORE-0003
Every relationship shall reference explicit object versions where regulatory reproducibility is required.

### DB-CORE-0004
The database shall support soft deletion and lifecycle states.

### DB-CORE-0005
The database shall store enough metadata to reconstruct a generated dossier baseline.

## Domain Model

### Core Tables

| Table | Purpose |
|---|---|
| regulatory_object | All domain objects with stable UUID |
| object_version | Immutable version history with JSON payload |
| object_relation | Explicit versioned relationships |
| event_log | Append-only event stream |
| approval_record | Workflow approval history |
| generated_artifact | Generated document records |
| baseline | Baseline snapshot metadata |
| baseline_item | Baseline object version references |

## Interfaces

- SQLAlchemy ORM — application data access
- Migration Scripts — schema versioning
- Repository Layer — domain object persistence
- Event Store — event log writes

## Data Model

### Complete DDL Sketch

```sql
CREATE TABLE regulatory_object (
  object_uuid BINARY(16) NOT NULL,
  object_type VARCHAR(64) NOT NULL,
  current_version INT NOT NULL DEFAULT 1,
  lifecycle_state VARCHAR(32) NOT NULL,
  owner_user_id VARCHAR(128),
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (object_uuid)
);

CREATE TABLE object_version (
  object_uuid BINARY(16) NOT NULL,
  version_no INT NOT NULL,
  payload_json JSON NOT NULL,
  status VARCHAR(32) NOT NULL,
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
  PRIMARY KEY (event_uuid)
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

- Schema migrations applied incrementally
- Object creation → version creation → state transitions logged
- Baselines captured before report generation
- Soft delete sets lifecycle_state to 'deleted'
- Approved versions are immutable (UPDATE blocked)

## Security

- Database access limited to application service account
- Audit logs are append-only
- Backup encryption for regulated environments
- Schema changes require migration review

## AI Support

- AI may suggest query optimizations
- AI may not modify schema directly

## Acceptance Criteria

- All domain objects can be persisted and retrieved.
- Object versions are immutable after approval.
- Event log is append-only and complete.
- Baseline captures exact object versions for reproducibility.
- Schema migrations are version-controlled.

## Open Questions

- Should UUIDs be stored as BINARY(16) or CHAR(36)?
- What indexing strategy is needed for large event logs?
- Should JSON schema validation be applied to payload_json?

## Initial DDL Sketch

```sql
CREATE TABLE regulatory_object (
  object_uuid BINARY(16) NOT NULL,
  object_type VARCHAR(64) NOT NULL,
  current_version INT NOT NULL DEFAULT 1,
  lifecycle_state VARCHAR(32) NOT NULL,
  owner_user_id VARCHAR(128),
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (object_uuid)
);

CREATE TABLE object_version (
  object_uuid BINARY(16) NOT NULL,
  version_no INT NOT NULL,
  payload_json JSON NOT NULL,
  status VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL,
  created_by VARCHAR(128) NOT NULL,
  PRIMARY KEY (object_uuid, version_no)
);
```

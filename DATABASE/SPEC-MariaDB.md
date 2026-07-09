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

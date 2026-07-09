# TASK-CORE-OBJECT-STORE-0001 — Implement Core Object Store

## Task ID

TASK-CORE-OBJECT-STORE-0001

## Title

Implement Core Object Store

## Source Requirements

- DB-OBJ-0001 through DB-OBJ-0010

## Goal

Implement the core object store database schema, SQLAlchemy ORM models, Pydantic schemas, repository pattern, lifecycle state machine, event log, and baseline support as the foundation for all regulatory domain objects.

## Background

The platform requires a reliable, auditable, and versioned object store for all regulatory content. This batch implements the core persistence layer that all domain services (Product, Claim, Risk, etc.) will build upon.

## Scope

- SQLAlchemy 2.0 ORM models for `regulatory_object`, `object_version`, `object_relation`, `event_log`, `approval_record`, `baseline`, `baseline_item`
- Pydantic v2 schemas for serialization and validation
- Alembic migration for initial schema creation
- Repository pattern with CRUD operations
- Lifecycle state machine with validated transitions
- Optimistic locking via `lock_version` column
- Immutable approved versions (enforced at repository level)
- Append-only event log
- Baseline creation and retrieval
- Soft deletion support
- Unit tests for all repository operations

## Non-Scope

- FastAPI endpoints — these will be added in a separate batch
- Domain-specific business logic (Product, Claim, Risk, etc.)
- Knowledge graph synchronization
- Event sourcing replay (beyond basic event log queries)

## Technical Approach

### Models

Use SQLAlchemy 2.0 declarative models with mapped_column syntax. Store UUIDs as BINARY(16) using `sqlalchemy.types.LargeBinary` with a helper function for hex conversion. Use JSON columns for payload storage.

### Repository

Implement `RegulatoryObjectRepository` in `src/orkp/db/repository.py` with methods:
- `create_object(object_type, payload, owner_user_id, created_by)`
- `get_by_uuid(uuid)`, `get_by_uuid_hex(uuid_hex)`
- `get_version(object_uuid, version_no)`
- `list_objects(object_type=None, lifecycle_state=None, limit=100, offset=0)`
- `create_version(object_uuid, payload, created_by)`
- `transition_state(object_uuid, new_state, actor_user_id, comments=None)`
- `soft_delete(object_uuid, actor_user_id)`
- `create_baseline(description, object_versions, created_by)`
- `get_baseline(baseline_uuid)`

### Lifecycle State Machine

Valid transitions:
- draft → in_review
- in_review → approved
- in_review → rejected
- in_review → draft
- approved → effective
- effective → obsolete
- rejected → draft

### Optimistic Locking

On update, compare `lock_version` with the value read at fetch time. Use `UPDATE ... WHERE lock_version = :old_version` and check affected rows.

### Immutable Approved Versions

The repository layer MUST reject any attempt to create a new version on an approved object. The `create_version` method checks `lifecycle_state == 'approved'` and raises `ValueError`.

## Acceptance Criteria

1. A draft object can be created, retrieved, and updated.
2. Multiple versions of the same object can be created (in draft state).
3. An object can transition through the full lifecycle: draft → in_review → approved → effective → obsolete.
4. An approved object version is immutable (new version creation fails).
5. Optimistic locking prevents concurrent overwrites.
6. The event log records every state change with actor identity and timestamp.
7. Soft-deleted objects are excluded from default queries.
8. A baseline can be created with specific object versions and later retrieved.
9. All state transitions are validated against the state machine.

## Unit Tests

- `test_create_draft_object` — creates and verifies initial state
- `test_create_version` — creates a new version and verifies version number
- `test_immutable_approved_version` — verifies approved version cannot be updated
- `test_optimistic_locking` — verifies concurrent update protection
- `test_lifecycle_transitions` — verifies each valid transition
- `test_invalid_transition` — verifies invalid transitions are rejected
- `test_event_log` — verifies events are recorded for each operation
- `test_baseline` — verifies baseline creation and retrieval
- `test_soft_delete` — verifies soft deletion behavior

## Integration Tests

- `test_repository_integration` — full lifecycle with repository

## Definition of Done

- SQLAlchemy models exist in `src/orkp/db/models.py`
- Pydantic schemas exist in `src/orkp/api/schemas.py`
- Repository exists in `src/orkp/db/repository.py`
- Alembic migration exists in `src/orkp/db/migrations/`
- All unit tests pass
- `python -m pytest -q` passes
- `python tools/spec_linter.py --strict` passes
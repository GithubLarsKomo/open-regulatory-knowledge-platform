# Performance Optimization Plan: Relation Validation Roundtrips

## Problem

The reproducible ORKP baseline shows no query explosion on the measured read paths: object listing, version history, relation listing and the FastAPI list path each execute one SQL statement per sample.

The first evidence-backed write hotspot is `RegulatoryObjectRepository.create_relation()`. On both Python 3.10 and 3.12 it executes five SQL statements for one valid relation when the caller flushes the pending insert:

1. source `ObjectVersion` lookup;
2. target `ObjectVersion` lookup;
3. source `RegulatoryObject` lookup;
4. target `RegulatoryObject` lookup;
5. relation `INSERT`.

The four reads exist to prove source/target versions and obtain object types for canonical relation-policy validation.

## Baseline

| Scenario | Python 3.10 | Python 3.12 | SQL statements |
|---|---:|---:|---:|
| `repository_create_relation` median | 1.694 ms | 1.359 ms | 5 |
| `repository_create_object` median | 1.059 ms | 0.976 ms | 3 |
| read/list scenarios | environment-dependent | environment-dependent | 1 each |

Hosted-runner timings are observational only. The deterministic performance gate for this slice is SQL statement count.

## Root cause

`create_relation()` calls `get_version()` twice and `get_by_uuid_including_deleted()` twice. Each helper correctly serves its general-purpose API, but composing four independent point queries is unnecessary when relation creation needs both endpoints as one validation context.

This is a local repository-layer inefficiency. No architecture change, cache, asynchronous processing, new infrastructure or schema change is justified.

## Selected optimization

Fetch the source and target endpoint contexts with one SQLAlchemy query joining `ObjectVersion` to `RegulatoryObject` and matching the two requested `(object_uuid, version_no)` pairs.

Build an in-memory mapping keyed by `(object_uuid, version_no)` and preserve the current validation order:

1. source version must exist;
2. target version must exist;
3. relation type must be canonical;
4. source/target object types must satisfy `validate_relation()`;
5. create the pending `ObjectRelation` exactly as before.

Expected valid-path SQL count after caller flush: **2** (one validation `SELECT` + one relation `INSERT`).

## Functional invariants

- Same public `create_relation()` signature and returned model.
- Same `InvalidRelationError` for missing source version.
- Same `InvalidRelationError` for missing target version.
- Same invalid-relation-type behavior and message contract.
- Same canonical source/target type validation through `validate_relation()`.
- Deleted objects remain eligible for type lookup exactly as with `get_by_uuid_including_deleted()`; only version existence and canonical type compatibility matter here.
- Same transactional behavior: method adds a pending relation but does not commit.
- Existing relation lifecycle and listing behavior are unchanged.

## Performance gate

For the deterministic SQLite harness:

- Before: `repository_create_relation` = 5 SQL statements/sample.
- Required after: `repository_create_relation` <= 2 SQL statements/sample.
- `repository_create_object` must remain 3 SQL statements/sample.
- Read/list scenarios must remain 1 SQL statement/sample.

Timing is recorded Before/After but is not a hard CI acceptance threshold on hosted runners.

## Functional gate

- Existing full pytest suite passes on Python 3.10 and 3.12.
- Existing relation repository tests pass unchanged.
- Add a focused regression test proving the successful relation-creation path uses at most two SQL statements including `flush()`.
- Add/retain tests for missing source version, missing target version, invalid relation type and incompatible endpoint types.

## Rejected alternatives

### Cache endpoint objects or versions
Rejected. It adds invalidation/lifecycle complexity and the baseline points to deterministic roundtrip overhead that can be removed directly.

### Parallelize the four reads
Rejected. Database roundtrips remain and transaction/session semantics become more complex.

### Add indexes
Rejected for this slice. The measured issue is statement count, not evidence of a scan or missing index. Endpoint keys are already modeled as point lookups.

### Bulk relation API
Potential future optimization for imports, but out of scope. First make the single-relation primitive efficient and verify it.

### Rewrite the repository layer
Rejected. The hotspot is local and has a small reversible solution.

## Risks

- Accidentally changing which validation error wins when more than one input is invalid.
- Mishandling source and target when both refer to the same object/version.
- Returning duplicate/join rows incorrectly.
- Changing deleted-object semantics.

Mitigations: preserve validation order, key results by UUID/version, add same-endpoint and invalid-input tests where needed, run full suite.

## Rollback

The change is isolated to relation endpoint validation in `repository.py` plus focused tests. Revert the optimization commit if functional tests fail or the SQL-count gate is not achieved.

## Stop rule

Stop after the valid relation path reaches two SQL statements and all functional gates pass. Do not optimize object creation or read paths in this slice; their current statement counts are separate evidence and require independent justification.

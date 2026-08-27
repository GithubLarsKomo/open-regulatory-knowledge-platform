# Performance Optimization Plan: Hybrid Keyword Retrieval

## Problem

The E2E performance baseline compares four representative ORKP workflows. The dominant measured database-roundtrip hotspot is hybrid keyword retrieval over 1,000 current Object Store objects.

Python 3.10 baseline:

| Workflow | SQL statements | Median |
|---|---:|---:|
| Hybrid keyword retrieval, 1,000 objects | **1,041** | **222.794 ms** |
| Baseline freeze, 100 items | 304 | 63.107 ms |
| Traceability graph, 51 nodes | 106 | 20.741 ms |
| PER DOCX render | 10 | 3.245 ms |

Hosted-runner timing is observational. SQL statement count is the deterministic gate.

## Root cause

`ObjectStoreKeywordRetrievalAdapter.search()` currently:

1. loads up to 5,000 non-deleted objects with `repo.list_objects()`;
2. calls `repo.get_version()` once per scanned object to load its current payload;
3. scores matching payloads in Python;
4. returns up to `keyword_limit` exact-version hits;
5. `HybridRetrievalService` separately revalidates each returned hit against the Object Store.

For the 1,000-object / 20-hit baseline this produces:

- 1 object-list query;
- 1,000 current-version queries;
- 40 exact-hit validation queries;
- total: **1,041 statements**.

The per-object current-version lookup is the first and overwhelmingly largest removable component.

## Selected optimization

Add a narrow DB-layer read query that loads non-deleted `RegulatoryObject` rows together with their current `ObjectVersion` in one joined SQL statement, preserving the existing `updated_at DESC` scan order and scan limit.

The keyword adapter will iterate these `(object, current_version)` pairs and keep its existing Python tokenization, matching, phrase bonus, scoring, deterministic sort and result limit unchanged.

## Performance hypothesis

For 1,000 scanned objects and 20 keyword hits:

- Before: 1,041 SQL statements.
- Expected after this slice: **<=41 SQL statements**.
- Mechanism: 1 joined scan query + the existing 2 validation queries for each of 20 returned hits.
- Expected statement reduction: at least 96%.

The remaining hit-validation reads are intentionally out of scope for this slice. They require independent evidence after the N+1 scan has been removed.

## Functional invariants

- Same public `ObjectStoreKeywordRetrievalAdapter.search()` API.
- Same `scan_limit` default and enforcement.
- Same exclusion of soft-deleted objects.
- Same exclusion of `ai_draft` hits.
- Same use of each object's exact `current_version`.
- Same tokenization and searchable payload representation.
- Same keyword coverage and phrase-bonus scoring.
- Same deterministic ranking/tie breaking.
- Same exact version references in returned hits.
- Same `HybridRetrievalService` validation of adapter hits.
- Same vector and graph retrieval behavior.
- Retrieval remains read-only.

## Regression gates

### Functional

- Existing hybrid retrieval and security tests pass unchanged.
- Current-version retrieval remains correct after creating a newer version.
- Deleted objects remain excluded.
- Result ordering and scoring remain deterministic.
- Full pytest suite passes on Python 3.10 and 3.12.

### Performance

- E2E `hybrid_keyword_1000`: **<=41 SQL statements**.
- Adapter-only scan: exactly 1 SQL statement independent of scanned-object count.
- Baseline freeze remains 304 statements unless independently changed.
- Graph traceability remains 106 statements unless independently changed.
- PER DOCX render remains 10 statements unless independently changed.
- Existing read/write baseline gates remain unchanged.

Timing distributions are recorded Before/After but are not hard CI gates.

## Rejected alternatives

### Push keyword matching into SQL

Rejected. It would change provider-neutral recursive JSON tokenization/search semantics and couple deterministic ranking to database-specific text behavior.

### Add full-text search infrastructure

Rejected. The measured N+1 can be removed without schema, index or infrastructure changes. Full-text search would be a separate product/architecture decision.

### Cache current versions

Rejected. It adds invalidation and consistency complexity while the roundtrip source can be removed directly.

### Batch or remove exact hit validation in the same slice

Rejected for this slice. The expected 1,041 -> 41 reduction already removes the dominant hotspot. Hit validation is security/correctness-sensitive and should be optimized only with a separate hypothesis and regression evidence if it remains material.

### Optimize graph and baseline creation simultaneously

Rejected. E2E measurement ranks them below retrieval, and parallel optimization would make causality and rollback less clear.

## Rollback

The change is limited to one DB read-query helper, the keyword adapter call site and focused tests. Revert the slice if result equivalence or the <=41-statement E2E gate fails.

## Stop rule

Stop when the 1,000-object E2E retrieval reaches <=41 SQL statements, all semantic tests remain green, and no unnecessary abstraction remains after simplification review. Do not optimize the remaining exact-hit validation in this slice.
# TASK: Optimize Hybrid Retrieval Exact-Hit Validation

## Objective

Reduce `hybrid_keyword_1000` from 41 SQL statements to 2 without weakening exact Object Store grounding or changing retrieval semantics.

## Baseline

- 1 keyword scan query
- 20 returned keyword hits
- 2 validation reads per hit
- total: 41 statements

## Root cause

`HybridRetrievalService` validates each hit through `get_by_uuid()` followed by `get_version()`. The validation is semantically necessary; the per-hit persistence access is not.

## Tasks

- [x] Add one set-oriented Object Store validation read for many exact references.
- [x] Preserve object-not-found vs version-not-found distinction with an outer join.
- [x] Prepare adapter-channel and UUID validation without changing first-error ordering.
- [x] Validate all prepared hits sequentially against the batched contexts.
- [x] Preserve object-type mismatch and `ai_draft` exclusion.
- [x] Keep graph seed validation unchanged.
- [x] Tighten the hybrid keyword query guard to exactly 2 statements for 10 hits.
- [ ] Run full Python 3.10 and 3.12 CI.
- [ ] Confirm persistent `hybrid_keyword_1000` E2E statement count is exactly 2.
- [ ] Confirm all other deterministic performance budgets remain unchanged.
- [ ] Run simplification pass and document closure.
- [ ] Merge only after both runtime matrices are green.

## Functional gate

- Existing hybrid retrieval semantics tests remain green.
- Unknown exact version remains rejected.
- Wrong object type remains rejected.
- Wrong adapter channel remains rejected.
- AI drafts remain excluded.
- Cross-channel exact-reference fusion remains unchanged.
- Retrieval remains read-only.

## Performance gate

- keyword scan: exactly 1 statement
- 10-hit keyword-only hybrid retrieval: exactly 2 statements
- `hybrid_keyword_1000`: exactly 2 statements
- no regression in baseline-create, traceability graph, PER render, repository reads or write budgets

## Compatibility

- Python 3.10 and 3.12
- SQLAlchemy 2.x
- SQLite CI semantics retained
- no schema migration
- no cache or external service

## Out of scope

- graph seed validation roundtrips
- vector provider implementation
- graph traversal optimization
- keyword scoring or full-text search
- schema/index redesign
- timing-based CI gates

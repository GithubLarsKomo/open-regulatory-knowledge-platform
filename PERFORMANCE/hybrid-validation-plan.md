# Performance Plan: Hybrid Retrieval Exact-Hit Validation

## Problem

The current `hybrid_keyword_1000` end-to-end scenario executes 41 SQL statements for 20 keyword hits. The keyword scan itself is already set-oriented and accounts for one statement. The remaining 40 statements come from exact Object Store validation in `HybridRetrievalService._validate_hit()`: one object lookup and one exact-version lookup for every returned hit.

## Baseline

- Scenario: `hybrid_keyword_1000`
- Objects scanned: 1,000
- Keyword results: 20
- SQL statements: 41
- Deterministic decomposition: 1 keyword scan + 20 x 2 exact-hit validation reads
- Timing is observational only; statement count is the performance gate.

## Root cause

Validation semantics require every adapter hit to be grounded against the Object Store before fusion. The semantics do not require a separate database roundtrip per hit. The current implementation couples validation order to persistence access and therefore creates an N+1 read pattern after retrieval.

## Selected optimization

Batch all valid exact `(object_uuid, object_version)` references from keyword, vector and graph hits into one read-only Object Store projection. Use an outer join so the in-memory validation phase can still distinguish:

1. invalid UUID;
2. object not found;
3. exact version not found;
4. object type mismatch;
5. `ai_draft` exclusion.

Channel validation and UUID parsing are prepared per hit without raising immediately. After the single batch read, hits are evaluated in the same keyword -> vector -> graph and within-adapter order as before, so the first failing hit remains authoritative.

## Expected effect

For `hybrid_keyword_1000` with 20 keyword hits and no vector/graph hits:

- 1 keyword scan statement;
- 1 batched exact-hit validation statement;
- target total: **2 SQL statements**.

The validation query count should remain one regardless of hit count, subject only to database parameter limits for unusually large adapter result sets.

## Preserved invariants

- Every hit is revalidated against the Object Store before fusion.
- Exact `(object_uuid, object_version)` identity is required.
- Missing object and missing version remain distinct errors.
- Adapter channel mismatch remains an error.
- Adapter-provided `object_type` must match the Object Store.
- `ai_draft` hits remain excluded.
- Retrieval ordering, scoring, weights, fusion and deterministic tie-breaking remain unchanged.
- Graph seed validation is out of scope and remains unchanged.
- Retrieval remains read-only.

## Rejected alternatives

- Removing exact-hit validation: rejected because it weakens grounding/security semantics.
- Trusting keyword hits because they originate from the Object Store: rejected because the hybrid service intentionally enforces a uniform adapter boundary.
- Per-adapter validation queries: better than N+1 but unnecessarily leaves up to three reads when one combined exact-reference set is sufficient.
- Cache: rejected because it adds invalidation complexity and is unnecessary for the measured problem.
- Async/parallel per-hit reads: rejected because it preserves N+1 behavior and increases complexity.
- Schema/index changes: not supported by the current evidence; the issue is roundtrip multiplicity.

## Measurement plan

1. Keep `ObjectStoreKeywordRetrievalAdapter.search()` at exactly one SQL statement.
2. Change the 10-hit hybrid performance guard from `<=21` to exactly `2` statements.
3. Run the persistent 1,000-object E2E scenario and require the deterministic statement count to fall from 41 to 2.
4. Run the complete test suite on Python 3.10 and 3.12.
5. Verify read/write/graph/PER deterministic budgets remain unchanged.

## Stop rule

Stop when the 20-hit E2E hybrid scenario executes exactly two SQL statements, all validation semantics remain covered by tests, both supported runtimes are green, and no additional abstraction is needed beyond one specialized read helper.

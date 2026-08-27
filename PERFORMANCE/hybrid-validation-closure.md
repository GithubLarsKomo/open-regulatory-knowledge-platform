# Optimization Closure: Hybrid Retrieval Exact-Hit Validation

## Scope

This closure covers only exact-hit Object Store validation after keyword, vector and graph adapters return retrieval hits. Adapter search behavior, graph seed validation, ranking, weighting, fusion and retrieval result semantics are unchanged.

## Baseline vs optimized state

| Metric | Before | After | Change |
|---|---:|---:|---:|
| SQL statements, `hybrid_keyword_1000` | 41 | 2 | -39 / -95.1% |
| SQL statements, original pre-keyword-optimization baseline | 1,041 | 2 | -1,039 / -99.8% cumulative |
| Python 3.12 median, hosted SQLite runner | 34.333 ms on prior 41-statement run | 28.891 ms | observational only |
| Baseline create, 100 items | 6 | 6 | unchanged |
| Traceability graph, 51 nodes | 3 | 3 | unchanged |
| PER DOCX render | 10 | 10 | unchanged |
| repository read baselines | 1 each | 1 each | unchanged |
| `create_object` | 3 | 3 | unchanged |
| `create_relation` | 2 | 2 | unchanged |

SQL statement count is deterministic and gating. Hosted-runner timing remains observational and is not used as an acceptance criterion.

## Mechanism confirmed

The previous 41-statement path decomposed exactly into:

- one set-oriented keyword scan;
- 20 hits x one object lookup;
- 20 hits x one exact-version lookup.

The optimized path now performs:

- one set-oriented keyword scan;
- one set-oriented exact-reference validation query for all returned hits;
- in-memory sequential semantic validation in the original hit order.

The Python 3.12 E2E harness produced **2/2/2/2/2 statements** for `hybrid_keyword_1000`, matching the performance hypothesis exactly.

## Validation equivalence

The batch query uses `RegulatoryObject` as the outer side and joins only requested exact `ObjectVersion` pairs. This preserves enough information to distinguish an existing object with a missing requested version from an object that does not exist at all.

Before the batch query, each hit is prepared in keyword -> vector -> graph order. Channel mismatches and invalid UUIDs are recorded rather than raised immediately. After the batch read, hits are evaluated in that same order. This preserves first-error behavior while avoiding per-hit database access.

Preserved checks:

- adapter channel must match the expected channel;
- object UUID must be valid;
- object must exist;
- exact requested version must exist;
- adapter `object_type` must match the Object Store;
- `ai_draft` hits remain excluded;
- every accepted hit remains grounded before fusion.

## Functional evidence

The first complete optimized Python 3.12 run passed:

- Ruff lint and formatting;
- **563 tests passed, 1 skipped**;
- read performance baseline;
- write performance baseline;
- end-to-end performance baseline;
- specification linter;
- backlog generator.

The only failing gate was generated-file synchronization because adding the two planning documents increased the specification linter's scanned-file count from 48 to 50. Adding this closure document raises the final expected count to 51; the generated report is synchronized in the same closure pass and the full Python 3.10/3.12 matrix is rerun afterward.

## Simplification pass

The final production change consists of:

1. one specialized read helper in the existing `read_queries` persistence module;
2. one two-phase validation block in `HybridRetrievalService`;
3. one tightened deterministic query-budget test.

No additional service class, cache, repository wrapper, concurrency layer or schema concept was introduced.

Deliberately not introduced:

- cache/invalidation state;
- async or parallel per-hit reads;
- trusted-adapter bypasses;
- schema or index changes;
- database-specific full-text behavior;
- temporary instrumentation in production code;
- separate batch query per retrieval channel.

A per-channel batching abstraction would add complexity while increasing the optimal one-query validation budget to as many as three statements. A single exact-reference set is therefore the simpler and faster end state.

## Regression guards

`tests/test_ai_retrieval_performance.py` now requires:

- keyword current-version scanning: exactly **1** SQL statement;
- 10-hit keyword-only hybrid retrieval: exactly **2** SQL statements total.

The persistent E2E harness independently verifies the 1,000-object / 20-hit scenario and exposes future regressions in CI artifacts.

Existing semantic tests continue to cover:

- unknown exact version rejection;
- wrong Object Store type rejection;
- wrong adapter channel rejection;
- AI draft exclusion;
- deterministic cross-channel fusion;
- read-only retrieval behavior.

## Residual performance opportunities

After this slice, the measured E2E deterministic statement budgets are:

1. PER DOCX render: **10** statements;
2. baseline create: **6** statements;
3. traceability graph: **3** statements;
4. hybrid keyword retrieval: **2** statements.

The hybrid retrieval path no longer represents a meaningful database-roundtrip hotspot. Further work on this path should require new evidence from CPU profiling, payload volume, production database execution plans or a different workload rather than attempting to reduce the remaining two structurally necessary reads.

## Stop decision

The selected target is met exactly on the first complete optimized runtime: `hybrid_keyword_1000` is reduced from 41 to 2 statements without weakening exact Object Store grounding. The slice should close after generated-file synchronization and a clean final Python 3.10/3.12 matrix run.

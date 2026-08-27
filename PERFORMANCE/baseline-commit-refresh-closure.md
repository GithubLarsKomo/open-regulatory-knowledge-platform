# Optimization Closure: Baseline Post-Commit Refresh

## Scope

This closure covers the remaining ORM lifecycle overhead around freshly created baselines after the earlier set-based baseline-freeze optimization. It does not change baseline persistence structure, exact-version validation, schema design, indexing or transaction ownership.

## Measured result

| Metric | Before | After | Change |
|---|---:|---:|---:|
| SQL statements, `baseline_create_100` | 6 | 5 | -1 / -16.7% |
| `per_render_docx` | 5 | 5 | unchanged |
| `graph_traceability_depth1_51` | 3 | 3 | unchanged |
| `hybrid_keyword_1000` | 2 | 2 | unchanged |
| repository read scenarios | 1 | 1 | unchanged |
| `create_object` | 3 | 3 | unchanged |
| `create_relation` | 2 | 2 | unchanged |

The first complete Python 3.12 verification run measured `baseline_create_100` at **5/5/5/5/5** statements while all other deterministic query budgets stayed unchanged. Timing remains observational and non-gating because hosted-runner variance is material.

## Mechanism confirmed

The baseline repository operation was already constant-cost and set-based. The six-statement end-to-end path consisted of four persistence statements, one ORM refresh and one deliberate verification read:

1. insert the `Baseline` row and obtain its identity;
2. load all exact requested version/object context with one composite set query;
3. bulk insert all frozen `BaselineItem` snapshots;
4. insert the `baseline_frozen` event;
5. after commit, refresh the expired `Baseline` ORM row only because its UUID was dereferenced again;
6. read all baseline items to verify the committed frozen set.

The optimized path captures the immutable generated UUID before commit and uses that value for the verification read. The verification itself remains intact. The resulting path is therefore four persistence statements plus one verification statement: **5 total**.

## Production alignment

The same lifecycle issue existed in baseline-creation services that constructed response payloads from just-created ORM objects only after commit. Risk Report, Performance Report and PER Report baseline creation now materialize their response values before commit, then commit, then return the already constructed response.

This does not bypass the commit. Response construction occurs inside the existing transaction try/rollback block, so a failed commit still raises and no response is returned.

## Preserved invariants

- Exact caller-selected object versions are frozen.
- Frozen `snapshot_json` remains the selected historical payload.
- Stored object types are unchanged.
- Soft-deleted exact historical versions remain eligible where previously supported.
- Missing exact versions still raise `BaselineValidationError`.
- One `baseline_frozen` event is emitted with the original requested item count.
- The 100-item E2E path still reads and verifies all committed baseline items.
- Commit/rollback ownership remains with the caller/service exactly as before.
- Default SQLAlchemy `expire_on_commit` behavior remains unchanged globally.
- No schema migration or persistence compatibility change is introduced.

## Functional evidence

The initial optimized Python 3.12 CI pass completed all substantive gates before the expected generated-file synchronization failure:

- Ruff lint and formatting passed;
- **566 tests passed, 1 skipped**;
- read performance baseline passed;
- write performance baseline passed;
- end-to-end performance baseline passed;
- `baseline_create_100` measured **5/5/5/5/5**;
- `per_render_docx` remained **5/5/5/5/5**;
- graph remained **3/3/3/3/3**;
- hybrid retrieval remained **2/2/2/2/2**;
- repository reads remained 1 statement;
- `create_object` remained 3 statements;
- `create_relation` remained 2 statements;
- strict specification linter passed semantically with zero duplicate, invalid or undefined IDs.

That run failed only because adding the plan and task changed the generated linter report's scanned-file count. This closure adds the final performance document; the repository-generated metadata is synchronized once at the final 57-file state before the merge gate is rerun on Python 3.10 and 3.12.

## Simplification pass

The final production change is deliberately small:

1. preserve generated baseline identity before commit when it is needed afterwards;
2. construct immutable baseline response payloads before commit instead of re-reading expired ORM state;
3. tighten the existing baseline performance guard to an exact five-statement budget.

Deliberately not introduced:

- global `expire_on_commit=False`;
- cache or invalidation logic;
- async or parallel persistence;
- new repository/service abstractions;
- schema or index changes;
- removal of exact-version validation;
- removal of the post-create verification read;
- timing-based CI thresholds;
- temporary production instrumentation.

## Regression guard

`tests/test_baseline_performance.py` now requires the full 100-item create + commit + verification operation to execute **exactly 5 SQL statements** while retaining the semantic assertions for item count, exact versions, object types, deleted-object historical snapshots and event payloads.

The E2E harness independently records the same high-level workflow on every CI matrix run.

## Stop decision

The targeted redundant ORM refresh has been removed and the remaining five statements are justified by the transaction plus deliberate verification. Reducing the benchmark to four by deleting verification would make the measurement weaker rather than the production path better; changing global session expiration semantics would have disproportionate correctness risk.

Baseline creation and PER rendering are now tied at five statements. Further optimization should be driven by new workload evidence rather than by pursuing a lower statement count for its own sake.

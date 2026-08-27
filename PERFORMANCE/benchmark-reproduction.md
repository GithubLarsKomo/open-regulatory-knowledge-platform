# ORKP Performance Baseline Reproduction

This baseline is the measurement entry point for the `optimize-software-performance` workflow.
It deliberately records evidence before authorizing code optimization.

## Scope

The first baseline covers five representative core paths:

1. repository object listing with 100 objects;
2. repository object listing with 1,000 objects;
3. version-history retrieval with 200 versions;
4. source-relation listing with 250 relations;
5. FastAPI end-to-end object listing with 500 objects.

The harness records wall-clock samples and SQL statement counts for every measured run.
It performs two warm-up executions and seven measured executions by default and reports median, p95, minimum and maximum timing.

## Reproduction

Install the project development dependencies and run:

```bash
python tools/performance_baseline.py --output performance-baseline.json
```

For a quick diagnostic run:

```bash
python tools/performance_baseline.py --warmups 1 --repetitions 3
```

The JSON result includes the Python, SQLAlchemy, FastAPI, SQLite and platform versions plus the source commit when executed in GitHub Actions.

## Measurement integrity

Timing values are observational in this first phase. Do **not** introduce a hard millisecond CI gate from GitHub-hosted runner timings alone. Compare timing only when workload and execution environment are materially equivalent.

SQL query counts are recorded separately because they are more deterministic and can expose N+1 behavior or additional database round trips even when wall-clock timings are noisy.

Every scenario validates the expected result cardinality before accepting a sample. A faster result that changes returned data is therefore not accepted as a valid performance result.

## Database limitation

The baseline uses SQLite with the same SQLAlchemy ORM models and repository/API code used by the test suite. This is appropriate for measuring Python/ORM/API overhead, result materialization and SQL statement count without external infrastructure noise.

It is **not** sufficient evidence for MariaDB optimizer behavior, network latency, lock contention or production-scale index performance. Before accepting database-specific optimization work, repeat the relevant candidate against an explicitly configured MariaDB integration workload and capture `EXPLAIN`/query-plan evidence where appropriate.

## Optimization gate

Do not change production code merely because a path appears expensive by inspection. The next phase must:

1. capture the baseline JSON from CI;
2. compare scaling behavior and SQL counts;
3. identify the dominant measurable hotspot;
4. formulate a performance hypothesis;
5. create `PERFORMANCE_PLAN.md` and a bounded implementation task;
6. verify functional equivalence and Before/After measurements on the same workload.

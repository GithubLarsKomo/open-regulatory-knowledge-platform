# TASK: Optimize Traceability Graph Roundtrips

## Objective

Reduce `graph_traceability_depth1_51` from **106 SQL statements to <=3** while preserving exact-version graph semantics and making query count scale with traversal depth instead of node count.

## Baseline

- Workload: 51 exact-version nodes, depth 1.
- Result size: 51 graph nodes.
- Current budget: **106 SQL statements**.
- Measurement: `tools/performance_e2e_baseline.py`.

## Root cause

The root is loaded twice with separate object/version reads; every adjacent node is then loaded with another pair of reads. Incoming and outgoing relations are also fetched separately.

## Implementation

- [ ] Add DB-layer set reads for exact object/version contexts.
- [ ] Add one active-relation query for an entire exact-version frontier.
- [ ] Preserve one-query typed root validation/materialization.
- [ ] Traverse breadth-first by exact `(uuid, version)` frontier sets.
- [ ] Batch materialize all discovered non-root nodes after traversal.
- [ ] Preserve incoming/outgoing active relation semantics.
- [ ] Preserve historical-version distinction and soft-deleted object projection.
- [ ] Preserve deterministic node/edge ordering and duplicate elimination.
- [ ] Do not add cache, indexes, schema changes, async logic or materialized graph state.

## Functional gate

- [ ] Existing `test_graph_projection.py` passes unchanged.
- [ ] Existing impact-analysis tests pass unchanged.
- [ ] Missing root version remains `ObjectVersionNotFoundError`.
- [ ] Incoming and outgoing relations both project correctly.
- [ ] Inactive relations remain excluded.
- [ ] Depth 2 still traverses across intermediate exact-version nodes.
- [ ] Full pytest suite passes on Python 3.10 and 3.12.

## Performance gate

- [ ] Depth 0 root-only projection executes 1 SQL statement.
- [ ] 51-node depth-1 star executes <=3 SQL statements.
- [ ] 51-node depth-2 graph executes <=4 SQL statements.
- [ ] Fixed-depth query count does not grow with frontier width.
- [ ] Baseline freeze remains 6 statements.
- [ ] Hybrid keyword retrieval remains 41 statements.
- [ ] PER DOCX render remains 10 statements.
- [ ] Existing read/write performance gates remain stable.

## Verification

```bash
python -m pytest -q
python tools/performance_baseline.py
python tools/performance_write_baseline.py
python tools/performance_e2e_baseline.py
```

## Definition of Done

Graph traversal uses depth-scaled set reads, semantic behavior is unchanged, deterministic query budgets hold for depth 0/1/2, both supported Python runtimes are green, and the simplification pass confirms that no unnecessary production abstraction or infrastructure was introduced.
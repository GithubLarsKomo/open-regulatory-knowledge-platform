# TASK — Hybrid keyword prefilter

- [x] Reproduce current E2E baseline on merged `master`.
- [x] Identify `hybrid_keyword_1000` as current highest-cost measured E2E scenario.
- [x] Trace cost to full candidate materialization plus repeated Python JSON serialization/tokenization.
- [ ] Add newest-window-preserving SQL superset prefilter with minimal projection.
- [ ] Keep canonical Python scoring/ranking unchanged.
- [ ] Add deterministic semantic/query-count regression tests.
- [ ] Run Python 3.10 and 3.12 CI.
- [ ] Compare read/write/E2E harnesses before/after.
- [ ] Run specification/backlog/generated-file gates.
- [ ] Perform simplification pass and document closure.
- [ ] Merge only if all functional gates are green and measured evidence supports the change.
# TASK — Hybrid keyword prefilter

- [x] Reproduce current E2E baseline on merged `master`.
- [x] Identify `hybrid_keyword_1000` as current highest-cost measured E2E scenario.
- [x] Trace cost to full candidate materialization plus repeated Python JSON serialization/tokenization.
- [x] Add newest-window-preserving SQL superset prefilter with minimal projection.
- [x] Keep canonical Python scoring/ranking unchanged.
- [x] Add deterministic semantic/query-count regression tests.
- [x] Add conservative Unicode fallback where SQL JSON serialization cannot be proven lossless.
- [x] Run Python 3.12 functional and performance harnesses on the implementation head.
- [x] Compare read/write/E2E harnesses before/after.
- [x] Perform simplification pass and document closure.
- [ ] Run final Python 3.10 and 3.12 CI on the complete closure head.
- [ ] Verify specification/backlog/generated-file gates on the complete closure head.
- [ ] Merge only if all final functional gates are green and measured evidence remains consistent.
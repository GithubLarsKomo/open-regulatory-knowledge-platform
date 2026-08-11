# Epic 007 — Report Generation MVP

Epic 007 implements `TASK-REPORT-0001` and `REP-PER-0001` through `REP-PER-0005` from `REPORTS/SPEC-PER.md`.

The first slice builds a deterministic JSON-first PER draft manifest from an existing frozen Performance Evaluation baseline. It reuses the Performance-domain baseline and section contracts instead of duplicating source-data selection or regulatory decisions.

Planned sequence:

1. baseline-only PER draft manifest and traceability appendix (`REP-PER-0001`, `REP-PER-0002`, `REP-PER-0005`)
2. explicit approved-vs-AI-draft content provenance (`REP-PER-0003`)
3. reproducible completeness section (`REP-PER-0004`)
4. DOCX/PDF/HTML rendering from the canonical manifest

Report generation must not bypass Product, Claim, Evidence, Performance or Risk approval rules. It consumes their frozen outputs.

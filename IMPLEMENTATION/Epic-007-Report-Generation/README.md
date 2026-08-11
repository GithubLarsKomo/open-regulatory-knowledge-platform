# Epic 007 — Report Generation MVP

Epic 007 implements `TASK-REPORT-0001` and `REP-PER-0001` through `REP-PER-0005` from `REPORTS/SPEC-PER.md`.

The implementation is baseline-first and JSON-canonical: document formats are projections of a frozen PER manifest, never independent regulatory data sources.

Implemented sequence:

1. baseline-only PER draft manifest and traceability appendix (`REP-PER-0001`, `REP-PER-0002`, `REP-PER-0005`)
2. explicit approved-vs-AI-draft content provenance (`REP-PER-0003`)
3. reproducible frozen completeness section (`REP-PER-0004`)
4. deterministic HTML/DOCX/PDF rendering from the canonical frozen manifest

Rendering uses the side-effect-free `PERDraftService.build_draft()` path and persists only the requested `per_report` artifact. The existing JSON draft endpoint continues to persist `per_draft` artifacts.

No third-party renderer is required by the MVP: HTML is UTF-8, DOCX is a deterministic minimal OOXML package, and PDF uses a deterministic WinAnsi text renderer that rejects unsupported characters rather than silently changing regulatory content.

Report generation must not bypass Product, Claim, Evidence, Performance or Risk approval rules. It consumes their frozen outputs.

A separate report approval/signature lifecycle, visual template designer, branding system and electronic-signature capability are not part of the numbered `REP-PER-0001` through `REP-PER-0005` MVP contract and must not be inferred as completed by this Epic.

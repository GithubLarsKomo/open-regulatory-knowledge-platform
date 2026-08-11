# Epic 007 — Report Generation MVP

Epic 007 implements `TASK-REPORT-0001` and `REP-PER-0001` through `REP-PER-0005` from `REPORTS/SPEC-PER.md`.

The implementation is baseline-first and JSON-canonical: document formats are projections of a frozen PER manifest, never independent regulatory data sources.

Implemented sequence:

1. baseline-only PER draft manifest and traceability appendix (`REP-PER-0001`, `REP-PER-0002`, `REP-PER-0005`)
2. explicit approved-vs-AI-draft content provenance (`REP-PER-0003`)
3. reproducible frozen completeness section (`REP-PER-0004`)
4. deterministic HTML/DOCX/PDF rendering from the canonical frozen manifest
5. persisted Core `report` aggregate with stable `report_uuid`, Product/Baseline pinning, draft/in-review/approved lifecycle, four-eyes approval, approved immutability and governed regeneration

The fifth slice restores an original `TASK-REPORT-0001` contract recorded in issue #1 that was broader than the later numbered-requirement implementation plan. The Core RegulatoryObject store already supplies UUID identity, versioning, lifecycle transitions, approval records, immutable approved versions and audit events, so no separate report table or migration is introduced.

A persisted PER Report stores the exact canonical `PERDraftPayload` snapshot and its SHA-256. Creation requires a derived PER Report baseline containing frozen completeness. Draft regeneration creates a new version of the same Report UUID. Regeneration after approval/effective/obsolete creates a new Report aggregate with an exact predecessor Report reference; it never mutates the approved object.

Rendering uses the side-effect-free `PERDraftService.build_draft()` path and persists only the requested `per_report` artifact. The existing JSON draft endpoint continues to persist `per_draft` artifacts.

No third-party renderer is required by the MVP: HTML is UTF-8, DOCX is a deterministic minimal OOXML package, and PDF uses a deterministic WinAnsi text renderer that rejects unsupported characters rather than silently changing regulatory content.

Report generation must not bypass Product, Claim, Evidence, Performance or Risk approval rules. It consumes their frozen outputs. PER Report approval additionally forbids self-approval by the Report owner or current-version author.

Visual template design/branding, electronic signatures, human review UI, multi-language generation and external office/PDF conversion services remain outside this Epic.

# Epic 007 — Deterministic PER Rendering

This design note covers the final planned Epic 007 rendering slice after `REP-PER-0001` through `REP-PER-0005` have been implemented at the canonical manifest level.

## Boundary

Rendered documents are projections of the frozen canonical `PERDraftPayload`. Rendering must never re-read live Product, Claim, Evidence, Study, relation, AI or gap state.

The renderer therefore consumes a side-effect-free `PERDraftService.build_draft()` result. The existing JSON draft-generation endpoint may continue to persist a `per_draft` artifact, but HTML/DOCX/PDF rendering must not create that intermediate artifact.

## Formats

- HTML: deterministic UTF-8 semantic document.
- DOCX: deterministic minimal OOXML package created with the Python standard library and fixed ZIP metadata.
- PDF: deterministic text PDF using the standard PDF Helvetica font with WinAnsi encoding. Unsupported non-WinAnsi characters are rejected rather than silently corrupted.

No third-party rendering dependency is added in the MVP.

## Artifact contract

Each successful render:

- is generated solely from one frozen PER baseline;
- produces deterministic bytes for the same baseline and format;
- computes SHA-256 over the exact rendered bytes;
- persists exactly one `GeneratedArtifact` with `artifact_type='per_report'` and the requested format;
- appends one `artifact_generated` audit event;
- returns the bytes through the REST API with media type, filename, artifact UUID and checksum headers.

## Non-scope

- visual template designer;
- corporate branding/theme management;
- electronic signatures;
- report approval workflow;
- external office/PDF conversion services.

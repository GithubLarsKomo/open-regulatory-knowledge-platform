# TASK-REPORT-0001 — Baseline-pinned deterministic PER JSON

Implements the first vertical slice of report generation:

- typed canonical PER report payload
- persistence through the generic Regulatory Object Store as `per_report`
- explicit product and baseline pinning
- approved-source filtering
- deterministic canonical JSON
- provenance markers
- traceability appendix
- structured completeness gaps
- domain service and API router
- service tests

## Architecture decision

No dedicated report table or migration is introduced. PER reports use the existing generic, versioned Regulatory Object Store so lifecycle, audit trail, optimistic locking, and approved-version immutability remain consistent with all other ORKP domains.

## Remaining integration step

Mount `create_per_report_router(get_repo)` in `src/orkp/api/main.py` after the existing domain routers. This is intentionally left visible in the draft PR because the GitHub connector only supports complete-file replacement for existing files and the application factory is a large shared file. The router itself is implemented and ready to mount.

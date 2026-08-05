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

## Integration status

`create_per_report_router(get_repo)` is mounted in `src/orkp/api/main.py`. Validation is rerun against `master` commit `202dbd367416c37a0d0c4b92cab56d7e44ef3895`, which contains the approved Epic 007 and incremental Ruff CI repairs.

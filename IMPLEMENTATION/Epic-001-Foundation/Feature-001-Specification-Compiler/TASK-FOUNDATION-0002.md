# TASK-FOUNDATION-0002
# Implement Specification ID Linter

## Source Requirements

- META-ID-0001
- META-TASK-0001

## Goal

Create a Python script that scans Markdown SPEC files, validates ID uniqueness and format compliance, detects obsolete IDs, and outputs a traceability CSV report.

## Background

The repository contains ~95 requirements across 15+ SPEC files. As the number of requirements grows, manual validation becomes error-prone. An automated linter ensures:

- All IDs follow the `PREFIX-DOMAIN-NNNN` format
- No duplicate IDs exist
- No obsolete IDs remain in active files
- Cross-references between files are valid

## Scope

- Python-based CLI tool
- Scan all `.md` files in the repository (configurable path)
- Extract requirement IDs using regex pattern `[A-Z]+-[A-Z]+-\d{4}`
- Validate format compliance per META-ID-0001
- Detect duplicate IDs across all scanned files
- Report IDs referencing non-existent source files
- Output a traceability CSV in the format `id,source_file,type,status`
- Report markdown summary of findings

## Non-scope

- Real-time file watching
- Integration with CI/CD pipelines (future)
- YAML or JSON configuration files
- GUI

## Technical Approach

1. Use Python 3.10+ with standard library only (no external dependencies)
2. Recursively discover `.md` files, excluding `.git` and node_modules
3. For each file, parse requirement IDs using regex
4. Build an in-memory index of all IDs with file paths
5. Validate:
   - Each ID matches `^[A-Z]+-[A-Z]+-\d{4}$`
   - No two files share the same ID
   - No ID references a file that does not exist
6. Generate CSV output
7. Generate a human-readable Markdown report

## Acceptance Criteria

1. Script runs against the ORKP repository and exits with code 0.
2. All existing IDs are detected and reported in the CSV.
3. A duplicate ID test case causes non-zero exit code.
4. An invalid format ID test case causes non-zero exit code.
5. Output CSV contains all columns: id, source_file, type, status.

## Unit Tests

- Test ID extraction from a Markdown string with multiple IDs
- Test duplicate detection with known duplicates
- Test invalid format detection (e.g. `REQ--0001`, `req-core-0001`)
- Test CSV output format matches expected columns

## Integration Tests

- Run linter on the ORKP repository and verify exit code 0
- Manually introduce a duplicate ID and verify exit code non-zero

## Definition of Done

- Script committed to `tools/spec_linter.py`
- Unit tests committed to `tests/test_spec_linter.py`
- README explains usage
- Run against ORKP repository passes cleanly
- CSV output matches TRACEABILITY/Requirements.csv format
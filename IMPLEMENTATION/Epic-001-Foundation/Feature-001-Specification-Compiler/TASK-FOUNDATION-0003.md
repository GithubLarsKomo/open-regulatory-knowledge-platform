# TASK-FOUNDATION-0003
# Generate Initial Task Backlog from SPEC Files

## Source Requirements

- META-TASK-0001

## Goal

Create a Python script that reads requirement IDs from Markdown SPEC files and generates a structured task backlog in Markdown and CSV formats.

## Background

The ORKP repository defines ~95 requirements across 15+ SPEC files but currently only has 3 tasks documented. To systematically plan implementation, a tool is needed that:

- Parses all SPEC files for requirement IDs
- Groups requirements by domain
- Generates task stubs with appropriate structure
- Outputs a backlog in human-readable (Markdown) and machine-readable (CSV) formats

## Scope

- Python-based CLI tool
- Read requirement IDs from Markdown files
- Group requirements by domain prefix (CORE, CLAIM, RISK, PERF, PROD, EVID, UI, etc.)
- Generate one task stub per domain group
- Each task stub includes: task ID, title, source requirement IDs, goal, scope, non-scope, acceptance criteria template
- Output Markdown backlog
- Output CSV backlog with columns: task_id, title, requirement_ids, epic, phase

## Non-scope

- Task dependency ordering
- Effort estimation
- Assignment tracking
- Integration with project management tools

## Technical Approach

1. Python 3.10+ with standard library only
2. Reuse the ID extraction logic from TASK-FOUNDATION-0002 (or share a module)
3. For each unique domain prefix found, generate a task
4. Task ID scheme: `TASK-{DOMAIN}-{NNNN}` where DOMAIN is derived from requirement prefix
5. Generate output in two formats:
   - `backlog.md` — Markdown with sections per domain
   - `backlog.csv` — CSV with columns: task_id, title, requirement_ids, epic, phase

## Acceptance Criteria

1. Script runs and produces `backlog.md` and `backlog.csv`.
2. All requirements with tasks already defined are excluded from generation.
3. Each generated task references at least one requirement ID.
4. Output Markdown is readable and well-formatted.
5. Output CSV can be imported into spreadsheet tools.

## Unit Tests

- Test domain grouping: requirements with CLAIM prefix grouped into one task
- Test exclusion: known task requirements excluded from generation
- Test CSV output format

## Integration Tests

- Run on ORKP repository and verify output files are non-empty
- Verify every requirement in the traceability CSV appears in at least one generated or existing task

## Definition of Done

- Script committed to `tools/backlog_generator.py`
- Unit tests committed to `tests/test_backlog_generator.py`
- Run against ORKP repository produces valid output
- Output backlog and traceability CSV are consistent
# Open Regulatory Knowledge Platform

**Status:** Initial specification repository  
**Date:** 2026-07-07

The Open Regulatory Knowledge Platform is a database-driven, API-first and AI-assisted architecture for technical documentation, regulatory submissions, performance evaluation, risk management and post-market documentation for IVD and medical devices.

The core principle is:

> Regulatory knowledge is the source of truth. Documents are generated views.

This repository contains the initial specification hierarchy for implementation planning.

## Project Structure

```
META/              — ID scheme, writing rules, task group config (task_groups.json)
DOMAIN/            — Domain SPEC files (Claim, Evidence, Performance, Product, Risk)
AI/ API/ ARCHITECTURE/ DATABASE/ GRAPH/ REPORTS/ SECURITY/ TESTING/ UI/ WORKFLOW/
tools/             — spec_linter.py, backlog_generator.py
tests/             — pytest test suite
TRACEABILITY/      — Generated reports (backlog.md, backlog.csv, Requirements.csv, lint_report.md)
.github/workflows/ — CI pipeline
```

## Development

### Prerequisites

- Python 3.10 or 3.12
- A virtual environment is recommended

### Setup

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows

# Install project with dev dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
make test
# or
python -m pytest -q
```

### Running the Specification Linter

```bash
make lint-specs
# or
python tools/spec_linter.py --path . --report TRACEABILITY/lint_report.md --strict
```

The linter scans all Markdown SPEC files, validates requirement ID format, detects duplicate definitions, reports referenced-but-undefined IDs, and outputs a traceability CSV.

### Regenerating Backlog and TASK.md

```bash
make backlog
# or
python tools/backlog_generator.py --path . --output-dir TRACEABILITY --task-md
```

The backlog generator reads requirement IDs from heading lines in SPEC files, groups them by domain (configured in `META/task_groups.json`), and generates:
- `TRACEABILITY/backlog.md` — Markdown backlog by epic
- `TRACEABILITY/backlog.csv` — CSV backlog
- `TASK.md` — Auto-generated SWE batch plan

### Full Quality Check

```bash
make quality
```

Runs tests, linter and backlog generation in sequence.

### Configuration

Task group definitions are stored in `META/task_groups.json` (JSON, no YAML dependency). Edit this file to add or modify domain groups, foundation tasks, or epics.

### CI (GitHub Actions)

The CI pipeline (`.github/workflows/ci.yml`) runs on push/PR to `master`/`main`:
1. Installs the project with dev dependencies
2. Runs `pytest`
3. Runs the linter in strict mode
4. Runs the backlog generator
5. Fails if generated files are not up-to-date

**Note:** To push the workflow file, your GitHub Personal Access Token must have the `workflow` scope.

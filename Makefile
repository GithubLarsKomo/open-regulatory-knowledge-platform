.PHONY: test lint-specs backlog quality clean

# Python command
PYTHON := python

# Tools
LINTER := $(PYTHON) tools/spec_linter.py
BACKLOG := $(PYTHON) tools/backlog_generator.py
PYTEST := $(PYTHON) -m pytest

# Paths
ROOT := .
TRACE := TRACEABILITY

test:
	$(PYTEST) -q

lint-specs:
	$(LINTER) --path $(ROOT) --report $(TRACE)/lint_report.md --strict

backlog:
	$(BACKLOG) --path $(ROOT) --output-dir $(TRACE) --task-md

quality: test lint-specs backlog
	@echo "✅ All quality checks passed."

clean:
	rm -rf .pytest_cache
	rm -rf __pycache__
	find . -name '*.pyc' -delete
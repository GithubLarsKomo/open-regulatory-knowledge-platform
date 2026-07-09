#!/usr/bin/env python3
"""Unit tests for backlog_generator.py."""

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.backlog_generator import (
    extract_requirements,
    find_markdown_files,
    generate_backlog,
    generate_csv_backlog,
    generate_markdown_backlog,
    group_requirements_by_domain,
    DOMAIN_GROUPS,
    EXISTING_TASKS,
    EXISTING_TASK_REQUIREMENTS,
)


class TestExtractRequirements(unittest.TestCase):
    """Tests for extracting requirements from files."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def _write_file(self, name: str, content: str) -> Path:
        path = self.tmpdir / name
        path.write_text(content, encoding='utf-8')
        return path

    def test_extracts_ids(self):
        f = self._write_file('SPEC-Claim.md', '### REQ-CLAIM-0001\n### REQ-CLAIM-0002\n')
        ids = extract_requirements(f)
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[0][0], 'REQ-CLAIM-0001')

    def test_skips_inline_code(self):
        f = self._write_file('SPEC.md', 'Example: `REQ-CORE-0001`\n### REQ-CORE-0002\n')
        ids = extract_requirements(f)
        self.assertEqual(len(ids), 1)
        self.assertEqual(ids[0][0], 'REQ-CORE-0002')

    def test_empty_file(self):
        f = self._write_file('SPEC.md', '# No requirements\n')
        ids = extract_requirements(f)
        self.assertEqual(len(ids), 0)


class TestFindMarkdownFiles(unittest.TestCase):
    """Tests for finding SPEC Markdown files."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_finds_spec_files(self):
        (self.tmpdir / 'SPEC.md').touch()
        (self.tmpdir / 'DOMAIN').mkdir()
        (self.tmpdir / 'DOMAIN' / 'SPEC-Claim.md').touch()
        (self.tmpdir / 'TASK.md').touch()
        (self.tmpdir / 'README.md').touch()

        files = find_markdown_files(self.tmpdir)
        # SPEC.md is in EXCLUDE_FILES, so only SPEC-Claim.md should be found
        self.assertEqual(len(files), 1)
        self.assertIn(self.tmpdir / 'DOMAIN' / 'SPEC-Claim.md', files)

    def test_excludes_dot_git(self):
        (self.tmpdir / '.git').mkdir()
        (self.tmpdir / '.git' / 'SPEC-Claim.md').touch()
        (self.tmpdir / 'SPEC-Claim.md').touch()
        files = find_markdown_files(self.tmpdir)
        self.assertEqual(len(files), 1)


class TestGroupRequirements(unittest.TestCase):
    """Tests for grouping requirements by domain."""

    def test_groups_by_prefix(self):
        reqs = {
            'REQ-CLAIM-0001': ['SPEC-Claim.md'],
            'REQ-CLAIM-0002': ['SPEC-Claim.md'],
            'REQ-RISK-0001': ['SPEC-Risk.md'],
        }
        groups = group_requirements_by_domain(reqs)
        self.assertIn('CLAIM', groups)
        self.assertIn('RISK', groups)
        self.assertEqual(len(groups['CLAIM']), 2)
        self.assertEqual(len(groups['RISK']), 1)

    def test_empty_requirements(self):
        groups = group_requirements_by_domain({})
        self.assertEqual(len(groups), 0)


class TestGenerateBacklog(unittest.TestCase):
    """Tests for backlog generation."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def _write_file(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def test_generates_tasks_from_requirements(self):
        self._write_file(self.tmpdir / 'SPEC-Claim.md', '### REQ-CLAIM-0001\n### REQ-CLAIM-0002\n')
        self._write_file(self.tmpdir / 'SPEC-Risk.md', '### REQ-RISK-0001\n')

        existing, generated = generate_backlog(self.tmpdir)
        # 3 existing tasks from EXISTING_TASKS
        self.assertEqual(len(existing), 3)
        # Should have generated tasks for CLAIM and RISK
        gen_task_ids = [t['task_id'] for t in generated]
        self.assertIn('TASK-CLAIM-0001', gen_task_ids)
        # RISK is generated after CORE, DB, ARCH which have no matching files,
        # so the counter makes it 0002
        self.assertIn('TASK-RISK-0002', gen_task_ids)

    def test_excludes_existing_task_requirements(self):
        self._write_file(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        existing, generated = generate_backlog(self.tmpdir)
        # REQ-CORE-0001 is in EXISTING_TASK_REQUIREMENTS, should not generate new task
        gen_req_ids = [r for t in generated for r in t['requirements']]
        self.assertNotIn('REQ-CORE-0001', gen_req_ids)

    def test_empty_repository(self):
        existing, generated = generate_backlog(self.tmpdir)
        self.assertEqual(len(existing), 3)  # Still has 3 existing tasks
        # No SPEC files to scan, so generated should be empty
        # (but may be empty list)
        self.assertIsInstance(generated, list)


class TestOutputFormat(unittest.TestCase):
    """Tests for output format correctness."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_csv_output_columns(self):
        existing = [{
            'task_id': 'TASK-FOUNDATION-0001',
            'title': 'Test Task',
            'requirements': ['REQ-CORE-0001'],
            'epic': 'Epic 001',
            'phase': '0',
        }]
        generated = []

        csv_path = self.tmpdir / 'backlog.csv'
        generate_csv_backlog(existing, generated, csv_path)

        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 2)  # header + 1 data row
        self.assertEqual(rows[0], ['task_id', 'title', 'requirement_ids', 'epic', 'phase'])

    def test_markdown_output(self):
        existing = [{
            'task_id': 'TASK-FOUNDATION-0001',
            'title': 'Test Task',
            'requirements': ['REQ-CORE-0001'],
            'epic': 'Epic 001',
            'phase': '0',
            'scope': 'Test scope',
        }]
        generated = []

        md_path = self.tmpdir / 'backlog.md'
        generate_markdown_backlog(existing, generated, md_path)

        content = md_path.read_text(encoding='utf-8')
        self.assertIn('TASK-FOUNDATION-0001', content)
        self.assertIn('Test Task', content)
        self.assertIn('REQ-CORE-0001', content)
        self.assertIn('Epic 001', content)

    def test_csv_contains_all_columns(self):
        existing = [{
            'task_id': 'TASK-FOUNDATION-0001',
            'title': 'Create Repository Skeleton',
            'requirements': ['REQ-CORE-0001', 'REQ-ARCH-0001'],
            'epic': 'Epic 001 — Specification Foundation',
            'phase': '0',
        }]
        generated = []

        csv_path = self.tmpdir / 'backlog.csv'
        generate_csv_backlog(existing, generated, csv_path)

        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['task_id'], 'TASK-FOUNDATION-0001')
        self.assertEqual(rows[0]['requirement_ids'], 'REQ-CORE-0001; REQ-ARCH-0001')


class TestExistingTasks(unittest.TestCase):
    """Tests for existing task definitions."""

    def test_existing_tasks_have_required_fields(self):
        for task_id, info in EXISTING_TASKS.items():
            self.assertIn('title', info, f"{task_id} missing title")
            self.assertIn('requirements', info, f"{task_id} missing requirements")
            self.assertIn('epic', info, f"{task_id} missing epic")
            self.assertIn('phase', info, f"{task_id} missing phase")
            self.assertGreater(len(info['requirements']), 0, f"{task_id} has no requirements")

    def test_existing_task_requirements_exist_in_set(self):
        for task_id, info in EXISTING_TASKS.items():
            for req in info['requirements']:
                self.assertIn(req, EXISTING_TASK_REQUIREMENTS,
                              f"{req} referenced by {task_id} but not in EXISTING_TASK_REQUIREMENTS")


class TestDomainGroups(unittest.TestCase):
    """Tests for domain group definitions."""

    def test_all_groups_have_required_fields(self):
        for group in DOMAIN_GROUPS:
            self.assertIn('prefix', group)
            self.assertIn('task_suffix', group)
            self.assertIn('title', group)
            self.assertIn('epic', group)
            self.assertIn('phase', group)
            self.assertIn('scope', group)

    def test_unique_prefixes(self):
        prefixes = [g['prefix'] for g in DOMAIN_GROUPS]
        self.assertEqual(len(prefixes), len(set(prefixes)), "Duplicate domain prefixes found")


if __name__ == '__main__':
    unittest.main()
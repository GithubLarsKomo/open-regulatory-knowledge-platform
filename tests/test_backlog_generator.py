#!/usr/bin/env python3
"""Unit tests for backlog_generator.py."""

import csv
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.backlog_generator import (
    extract_requirement_ids,
    find_markdown_files,
    generate_backlog,
    generate_csv_backlog,
    generate_markdown_backlog,
    generate_task_md,
    collect_definitions,
    is_definition_file,
    is_heading_line,
    load_config,
)


class TestIsHeadingLine(unittest.TestCase):
    def test_heading_level_1(self):
        self.assertTrue(is_heading_line('# Purpose'))
    def test_heading_level_2(self):
        self.assertTrue(is_heading_line('## Purpose'))
    def test_heading_level_3(self):
        self.assertTrue(is_heading_line('### REQ-CORE-0001'))
    def test_heading_level_4(self):
        self.assertTrue(is_heading_line('#### Subsection'))
    def test_not_heading(self):
        self.assertFalse(is_heading_line('Some prose text'))
        self.assertFalse(is_heading_line('- list item'))
        self.assertFalse(is_heading_line('| table | cell |'))


class TestExtractRequirementIds(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)
    def _write(self, name, content):
        p = self.tmpdir / name
        p.write_text(content, encoding='utf-8')
        return p

    def test_extracts_ids_from_headings(self):
        f = self._write('SPEC-Claim.md', '### REQ-CLAIM-0001\n### REQ-CLAIM-0002\n')
        ids = extract_requirement_ids(f)
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[0], 'REQ-CLAIM-0001')

    def test_skips_ids_in_prose(self):
        f = self._write('SPEC.md', '# Overview\nREQ-CORE-0001 is a req.\n### REQ-CORE-0002\n')
        ids = extract_requirement_ids(f)
        self.assertEqual(len(ids), 1)
        self.assertEqual(ids[0], 'REQ-CORE-0002')

    def test_skips_inline_code(self):
        f = self._write('SPEC.md', '`REQ-CORE-0001`\n### REQ-CORE-0002\n')
        ids = extract_requirement_ids(f)
        self.assertEqual(len(ids), 1)

    def test_empty_file(self):
        f = self._write('SPEC.md', '# No IDs\n')
        ids = extract_requirement_ids(f)
        self.assertEqual(len(ids), 0)

    def test_unique_ids(self):
        f = self._write('SPEC.md', '### REQ-CORE-0001\n### REQ-CORE-0001\n')
        ids = extract_requirement_ids(f)
        self.assertEqual(len(ids), 1)


class TestFindMarkdownFiles(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_finds_spec_files_including_root(self):
        (self.tmpdir / 'SPEC.md').touch()
        (self.tmpdir / 'DOMAIN').mkdir()
        (self.tmpdir / 'DOMAIN' / 'SPEC-Claim.md').touch()
        (self.tmpdir / 'TASK.md').touch()
        (self.tmpdir / 'README.md').touch()
        files = find_markdown_files(self.tmpdir)
        self.assertIn(self.tmpdir / 'SPEC.md', files)
        self.assertIn(self.tmpdir / 'DOMAIN' / 'SPEC-Claim.md', files)

    def test_excludes_dot_git(self):
        (self.tmpdir / '.git').mkdir()
        (self.tmpdir / '.git' / 's.md').touch()
        (self.tmpdir / 'SPEC.md').touch()
        files = find_markdown_files(self.tmpdir)
        self.assertEqual(len(files), 1)

    def test_excludes_generated_files(self):
        (self.tmpdir / 'TASK.md').touch()
        (self.tmpdir / 'SPEC.md').touch()
        files = find_markdown_files(self.tmpdir)
        self.assertIn(self.tmpdir / 'SPEC.md', files)
        # TASK.md is in GENERATED_FILES
        self.assertNotIn(self.tmpdir / 'TASK.md', files)


class TestIsDefinitionFile(unittest.TestCase):
    def test_spec_md(self):
        self.assertTrue(is_definition_file('SPEC.md'))
    def test_spec_clain(self):
        self.assertTrue(is_definition_file('DOMAIN/SPEC-Claim.md'))
    def test_req_meta(self):
        self.assertTrue(is_definition_file('META/REQ-META.md'))
    def test_task_md(self):
        self.assertFalse(is_definition_file('TASK.md'))
    def test_readme_md(self):
        self.assertFalse(is_definition_file('README.md'))
    def test_glossary_md(self):
        self.assertFalse(is_definition_file('GLOSSARY.md'))
    def test_idscheme_not_definition(self):
        self.assertFalse(is_definition_file('META/SPEC-IDScheme.md'))


class TestCollectDefinitions(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)
    def _write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def test_root_spec_is_scanned(self):
        self._write(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        defs = collect_definitions(self.tmpdir)
        self.assertIn('REQ-CORE-0001', defs)

    def test_generated_files_ignored(self):
        self._write(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        self._write(self.tmpdir / 'TASK.md', '### TASK-PROD-0001\n')
        defs = collect_definitions(self.tmpdir)
        self.assertIn('REQ-CORE-0001', defs)
        self.assertNotIn('TASK-PROD-0001', defs.keys())


class TestLoadConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        (self.tmpdir / 'META').mkdir(parents=True, exist_ok=True)
    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_loads_valid_config(self):
        cfg = {
            "foundation_tasks": [{"task_id": "TASK-X-0001", "title": "X", "requirements": ["REQ-X-0001"], "epic": "E", "phase": "0"}],
            "domain_groups": [{"prefix": "REQ-X", "task_suffix": "X", "title": "X", "epic": "E", "phase": "1", "scope": "S."}]
        }
        (self.tmpdir / 'META' / 'task_groups.json').write_text(json.dumps(cfg), encoding='utf-8')
        loaded = load_config(self.tmpdir)
        self.assertEqual(len(loaded['foundation_tasks']), 1)
        self.assertEqual(len(loaded['domain_groups']), 1)

    def test_raises_on_missing(self):
        with self.assertRaises(FileNotFoundError):
            load_config(self.tmpdir)


class TestGenerateBacklog(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        (self.tmpdir / 'META').mkdir(parents=True, exist_ok=True)
        cfg = {
            "foundation_tasks": [{"task_id": "TASK-FOUNDATION-0001", "title": "Foundation", "requirements": ["REQ-CORE-0001"], "epic": "Epic 001", "phase": "0", "scope": ""}],
            "domain_groups": [
                {"prefix": "REQ-CLAIM", "task_suffix": "CLAIM", "title": "Claim Domain", "epic": "Epic 004", "phase": "2", "scope": "C."},
                {"prefix": "REQ-RISK", "task_suffix": "RISK", "title": "Risk Domain", "epic": "Epic 005", "phase": "2", "scope": "R."},
            ]
        }
        (self.tmpdir / 'META' / 'task_groups.json').write_text(json.dumps(cfg), encoding='utf-8')
    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)
    def _write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def test_generates_tasks_from_requirements(self):
        self._write(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        self._write(self.tmpdir / 'SPEC-Claim.md', '### REQ-CLAIM-0001\n### REQ-CLAIM-0002\n')
        self._write(self.tmpdir / 'SPEC-Risk.md', '### REQ-RISK-0001\n')
        f, g = generate_backlog(self.tmpdir)
        self.assertEqual(len(f), 1)
        self.assertEqual(len(g), 2)
        ids = [t['task_id'] for t in g]
        self.assertIn('TASK-CLAIM-0001', ids)
        self.assertIn('TASK-RISK-0001', ids)

    def test_excludes_foundation_reqs(self):
        self._write(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        self._write(self.tmpdir / 'SPEC-Claim.md', '### REQ-CLAIM-0001\n')
        f, g = generate_backlog(self.tmpdir)
        gen_reqs = [r for t in g for r in t['requirements']]
        self.assertNotIn('REQ-CORE-0001', gen_reqs)
        self.assertIn('REQ-CLAIM-0001', gen_reqs)

    def test_empty_repository(self):
        # Empty repo with a foundation task referencing an undefined req -> ValueError
        with self.assertRaises(ValueError):
            generate_backlog(self.tmpdir)

    def test_deterministic_task_ids(self):
        self._write(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        self._write(self.tmpdir / 'SPEC-Claim.md', '### REQ-CLAIM-0001\n')
        _, g1 = generate_backlog(self.tmpdir)
        _, g2 = generate_backlog(self.tmpdir)
        self.assertEqual([t['task_id'] for t in g1], [t['task_id'] for t in g2])

    def test_stable_output_repeated_runs(self):
        self._write(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        self._write(self.tmpdir / 'SPEC-Claim.md', '### REQ-CLAIM-0001\n### REQ-CLAIM-0002\n')
        f1, g1 = generate_backlog(self.tmpdir)
        f2, g2 = generate_backlog(self.tmpdir)
        self.assertEqual(g1, g2)
        self.assertEqual(f1, f2)


class TestUndefinedRequirements(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        (self.tmpdir / 'META').mkdir(parents=True, exist_ok=True)
    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_undefined_foundation_task_req_reported(self):
        """Foundation task referencing undefined requirement should raise ValueError."""
        cfg = {
            "foundation_tasks": [{
                "task_id": "TASK-BAD-0001",
                "title": "Bad Task",
                "requirements": ["REQ-NONEXISTENT-0001"],
                "epic": "Epic X",
                "phase": "0",
                "scope": ""
            }],
            "domain_groups": []
        }
        (self.tmpdir / 'META' / 'task_groups.json').write_text(json.dumps(cfg), encoding='utf-8')
        with self.assertRaises(ValueError):
            generate_backlog(self.tmpdir)


class TestOutputFormat(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_csv_columns(self):
        f = [{'task_id': 'TASK-X-0001', 'title': 'X', 'requirements': ['REQ-X-0001'], 'epic': 'E', 'phase': '0'}]
        p = self.tmpdir / 'b.csv'
        generate_csv_backlog(f, [], p)
        with open(p, newline='', encoding='utf-8') as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[0], ['task_id', 'title', 'requirement_ids', 'epic', 'phase'])
        self.assertEqual(len(rows), 2)

    def test_markdown_output(self):
        f = [{'task_id': 'TASK-X-0001', 'title': 'X Task', 'requirements': ['REQ-X-0001'], 'epic': 'EpiX', 'phase': '0', 'scope': 'S.'}]
        p = self.tmpdir / 'b.md'
        generate_markdown_backlog(f, [], p)
        c = p.read_text(encoding='utf-8')
        self.assertIn('TASK-X-0001', c)
        self.assertIn('X Task', c)

    def test_task_md_output(self):
        f = [{'task_id': 'TASK-F-0001', 'title': 'Foundation', 'requirements': ['REQ-CORE-0001'], 'epic': 'E1', 'phase': '0', 'scope': 'S.'}]
        g = [{'task_id': 'TASK-C-0001', 'title': 'Claim', 'requirements': ['REQ-CLAIM-0001'], 'epic': 'E2', 'phase': '2', 'scope': 'C.'}]
        p = self.tmpdir / 'TASK.md'
        generate_task_md(f, g, p)
        c = p.read_text(encoding='utf-8')
        self.assertIn('TASK-F-0001', c)
        self.assertIn('TASK-C-0001', c)
        self.assertIn('Foundation.', c)

    def test_dynamic_date(self):
        f = [{'task_id': 'TASK-X-0001', 'title': 'X', 'requirements': ['REQ-X-0001'], 'epic': 'E', 'phase': '0'}]
        p = self.tmpdir / 'b.md'
        generate_markdown_backlog(f, [], p)
        c = p.read_text(encoding='utf-8')
        self.assertIn(date.today().isoformat(), c)


if __name__ == '__main__':
    unittest.main()
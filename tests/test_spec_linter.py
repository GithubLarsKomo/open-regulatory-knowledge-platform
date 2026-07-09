#!/usr/bin/env python3
"""Unit tests for spec_linter.py."""

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add parent directory to path so we can import tools
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.spec_linter import (
    ID_PATTERN,
    extract_ids_from_file,
    find_markdown_files,
    generate_csv,
    generate_report,
    is_definition_file,
    lint_repository,
    validate_format,
    LintResult,
)


class TestValidateFormat(unittest.TestCase):
    """Tests for the validate_format function."""

    def test_valid_format(self):
        self.assertTrue(validate_format('REQ-CORE-0001'))
        self.assertTrue(validate_format('DB-CORE-0001'))
        self.assertTrue(validate_format('API-REST-0001'))
        self.assertTrue(validate_format('TASK-FOUNDATION-0001'))
        self.assertTrue(validate_format('META-ID-0001'))

    def test_invalid_format_lowercase(self):
        self.assertFalse(validate_format('req-core-0001'))

    def test_invalid_format_missing_prefix(self):
        self.assertFalse(validate_format('-CORE-0001'))

    def test_invalid_format_missing_domain(self):
        self.assertFalse(validate_format('REQ--0001'))

    def test_invalid_format_wrong_separator(self):
        self.assertFalse(validate_format('REQ_CORE_0001'))

    def test_invalid_format_too_few_digits(self):
        self.assertFalse(validate_format('REQ-CORE-001'))

    def test_invalid_format_too_many_digits(self):
        self.assertFalse(validate_format('REQ-CORE-00001'))

    def test_invalid_format_extra_suffix(self):
        self.assertFalse(validate_format('REQ-CORE-0001-EXTRA'))


class TestExtractIds(unittest.TestCase):
    """Tests for ID extraction from files."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def _write_file(self, name: str, content: str) -> Path:
        path = self.tmpdir / name
        path.write_text(content, encoding='utf-8')
        return path

    def test_extract_single_id(self):
        f = self._write_file('test.md', '### REQ-CORE-0001\nSome requirement text.\n')
        ids = extract_ids_from_file(f)
        self.assertEqual(len(ids), 1)
        self.assertEqual(ids[0][0], 'REQ-CORE-0001')
        self.assertTrue(ids[0][2])  # is_def

    def test_extract_multiple_ids(self):
        f = self._write_file('test.md', (
            '### REQ-CORE-0001\n'
            '### REQ-CORE-0002\n'
            '### DB-CORE-0001\n'
        ))
        ids = extract_ids_from_file(f)
        self.assertEqual(len(ids), 3)
        self.assertEqual([id_ for id_, _, _ in ids],
                         ['REQ-CORE-0001', 'REQ-CORE-0002', 'DB-CORE-0001'])

    def test_extract_no_ids(self):
        f = self._write_file('test.md', '# Just a heading\n\nSome text without IDs.\n')
        ids = extract_ids_from_file(f)
        self.assertEqual(len(ids), 0)

    def test_extract_id_in_table(self):
        f = self._write_file('test.md', '| REQ-CORE-0001 | SPEC.md | functional | draft |\n')
        ids = extract_ids_from_file(f)
        self.assertEqual(len(ids), 1)
        self.assertEqual(ids[0][0], 'REQ-CORE-0001')
        self.assertFalse(ids[0][2])  # not a definition in a table

    def test_extract_ids_with_duplicates(self):
        f = self._write_file('test.md', (
            '### REQ-CORE-0001\n'
            '### REQ-CORE-0001\n'
        ))
        ids = extract_ids_from_file(f)
        self.assertEqual(len(ids), 2)


class TestLintRepository(unittest.TestCase):
    """Integration-style tests for lint_repository."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def _write_file(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def test_clean_repository_no_issues(self):
        self._write_file(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        self._write_file(self.tmpdir / 'DOMAIN' / 'SPEC-Claim.md', '### REQ-CLAIM-0001\n')
        result = lint_repository(self.tmpdir)
        self.assertEqual(result.total_ids, 2)
        self.assertEqual(len(result.duplicates), 0)
        self.assertEqual(len(result.invalid_format), 0)
        self.assertEqual(len(result.errors), 0)
        self.assertFalse(result.has_issues)

    def test_duplicate_ids_detected(self):
        self._write_file(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        self._write_file(self.tmpdir / 'DOMAIN' / 'SPEC-Other.md', '### REQ-CORE-0001\n')
        result = lint_repository(self.tmpdir)
        self.assertEqual(len(result.duplicates), 1)
        self.assertEqual(result.duplicates[0][0], 'REQ-CORE-0001')
        self.assertTrue(result.has_issues)

    def test_invalid_format_detected(self):
        self._write_file(self.tmpdir / 'SPEC.md', '### REQ-core-0001\n')
        result = lint_repository(self.tmpdir)
        self.assertEqual(len(result.invalid_format), 1)
        self.assertEqual(result.invalid_format[0][0], 'REQ-core-0001')
        self.assertTrue(result.has_issues)

    def test_reference_without_definition_detected(self):
        self._write_file(self.tmpdir / 'TASK.md', '### REQ-CORE-0001\n')
        result = lint_repository(self.tmpdir)
        self.assertEqual(len(result.errors), 1)
        self.assertIn('never defined', result.errors[0])
        self.assertTrue(result.has_issues)

    def test_exclude_dirs_ignored(self):
        self._write_file(self.tmpdir / '.git' / 'config.md', '### REQ-CORE-0001\n')
        self._write_file(self.tmpdir / 'node_modules' / 'pkg' / 'readme.md', '### REQ-CORE-0002\n')
        self._write_file(self.tmpdir / 'SPEC.md', '### REQ-CORE-0003\n')
        result = lint_repository(self.tmpdir)
        self.assertEqual(result.total_ids, 1)
        self.assertEqual(result.ids_found.get('REQ-CORE-0003', [])[0][0], 'SPEC.md')

    def test_empty_repository(self):
        result = lint_repository(self.tmpdir)
        self.assertEqual(result.total_ids, 0)
        self.assertEqual(len(result.duplicates), 0)
        self.assertEqual(result.files_scanned, 0)


class TestGenerateCsv(unittest.TestCase):
    """Tests for CSV output generation."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_csv_output_format(self):
        result = LintResult()
        result.ids_found = {
            'REQ-CORE-0001': [('SPEC.md', 3)],
            'REQ-CLAIM-0001': [('DOMAIN/SPEC-Claim.md', 5)],
            'DB-CORE-0001': [('DATABASE/SPEC-MariaDB.md', 7)],
        }
        result.files_scanned = 3

        csv_path = self.tmpdir / 'output.csv'
        generate_csv(result, csv_path, self.tmpdir)

        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 4)  # header + 3 data rows
        self.assertEqual(rows[0], ['id', 'source_file', 'type', 'status'])
        # Check all IDs are present
        row_ids = [r[0] for r in rows[1:]]
        self.assertIn('REQ-CORE-0001', row_ids)
        self.assertIn('REQ-CLAIM-0001', row_ids)
        self.assertIn('DB-CORE-0001', row_ids)

    def test_csv_with_duplicates(self):
        result = LintResult()
        result.ids_found = {'REQ-CORE-0002': [('SPEC.md', 5)]}
        result.duplicates = [
            ('REQ-CORE-0001', [('SPEC.md', 3), ('SPEC-Other.md', 7)], 1, 'definition'),
        ]

        csv_path = self.tmpdir / 'output.csv'
        generate_csv(result, csv_path, self.tmpdir)

        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Header + 1 unique + 1 duplicate
        self.assertEqual(len(rows), 3)
        row_ids = [r[0] for r in rows[1:]]
        self.assertIn('REQ-CORE-0001', row_ids)
        self.assertIn('REQ-CORE-0002', row_ids)

    def test_csv_type_inference(self):
        result = LintResult()
        result.ids_found = {
            'REQ-CORE-0001': [('SPEC.md', 1)],
            'API-REST-0001': [('API/SPEC-REST.md', 1)],
            'TEST-VAL-0001': [('TESTING/SPEC-Validation.md', 1)],
            'TASK-CORE-0001': [('TASKS/task.md', 1)],
        }

        csv_path = self.tmpdir / 'output.csv'
        generate_csv(result, csv_path, self.tmpdir)

        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            types = {row['id']: row['type'] for row in reader}

        self.assertEqual(types['REQ-CORE-0001'], 'functional')
        self.assertEqual(types['API-REST-0001'], 'api')
        self.assertEqual(types['TEST-VAL-0001'], 'test')
        self.assertEqual(types['TASK-CORE-0001'], 'task')


class TestGenerateReport(unittest.TestCase):
    """Tests for Markdown report generation."""

    def test_report_no_issues(self):
        result = LintResult()
        result.files_scanned = 5
        result.ids_found = {'REQ-CORE-0001': [('SPEC.md', 1)]}
        report = generate_report(result, Path('/repo'))
        self.assertIn('No issues found', report)
        self.assertIn('REQ', report)
        self.assertIn('1', report)
        self.assertIn('5', report)

    def test_report_with_duplicates(self):
        result = LintResult()
        result.files_scanned = 2
        result.ids_found = {}
        result.duplicates = [
            ('REQ-CORE-0001', [('SPEC.md', 3), ('SPEC-Other.md', 7)], 1, 'definition'),
        ]
        report = generate_report(result, Path('/repo'))
        self.assertIn('Duplicate Definitions', report)
        self.assertIn('REQ-CORE-0001', report)

    def test_report_with_invalid_format(self):
        result = LintResult()
        result.files_scanned = 1
        result.ids_found = {}
        result.invalid_format = [
            ('req-core-0001', 'SPEC.md', 3),
        ]
        report = generate_report(result, Path('/repo'))
        self.assertIn('Invalid Format IDs', report)
        self.assertIn('req-core-0001', report)


class TestFindMarkdownFiles(unittest.TestCase):
    """Tests for Markdown file discovery."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_finds_md_files(self):
        (self.tmpdir / 'a.md').touch()
        (self.tmpdir / 'sub').mkdir()
        (self.tmpdir / 'sub' / 'b.md').touch()
        files = find_markdown_files(self.tmpdir)
        self.assertEqual(len(files), 2)

    def test_excludes_dot_git(self):
        (self.tmpdir / '.git').mkdir()
        (self.tmpdir / '.git' / 'config.md').touch()
        (self.tmpdir / 'SPEC.md').touch()
        files = find_markdown_files(self.tmpdir)
        self.assertEqual(len(files), 1)

    def test_excludes_node_modules(self):
        (self.tmpdir / 'node_modules').mkdir()
        (self.tmpdir / 'node_modules' / 'pkg.md').touch()
        (self.tmpdir / 'readme.md').touch()
        files = find_markdown_files(self.tmpdir)
        self.assertEqual(len(files), 1)


class TestIsDefinitionFile(unittest.TestCase):
    """Tests for is_definition_file."""

    def test_spec_md(self):
        self.assertTrue(is_definition_file('SPEC.md'))

    def test_spec_domain(self):
        self.assertTrue(is_definition_file('DOMAIN/SPEC-Claim.md'))

    def test_spec_meta(self):
        self.assertTrue(is_definition_file('META/REQ-META.md'))

    def test_task_md(self):
        self.assertFalse(is_definition_file('TASK.md'))

    def test_readme_md(self):
        self.assertFalse(is_definition_file('README.md'))

    def test_glossary_md(self):
        self.assertFalse(is_definition_file('GLOSSARY.md'))

    def test_task_file(self):
        self.assertTrue(is_definition_file('IMPLEMENTATION/Epic-001/TASK-FOUNDATION-0001.md'))

    def test_spec_idscheme_is_not_definition(self):
        self.assertFalse(is_definition_file('META/SPEC-IDScheme.md'))

    def test_glossary_md(self):
        self.assertFalse(is_definition_file('GLOSSARY.md'))

    def test_task_file_is_definition(self):
        self.assertTrue(is_definition_file('IMPLEMENTATION/Epic-001-Foundation/Feature-001-Specification-Compiler/TASK-FOUNDATION-0002.md'))


class TestIdPattern(unittest.TestCase):
    """Tests for the ID regex pattern."""

    def test_pattern_matches_valid_ids(self):
        text = 'REQ-CORE-0001 and DB-CORE-0001 and API-REST-0001'
        matches = ID_PATTERN.findall(text)
        self.assertEqual(matches, ['REQ-CORE-0001', 'DB-CORE-0001', 'API-REST-0001'])

    def test_pattern_does_not_match_invalid(self):
        text = 'REQ--0001 REQ-CORE-001'
        matches = ID_PATTERN.findall(text)
        self.assertEqual(matches, [])

    def test_pattern_requires_word_boundary(self):
        text = 'XREQ-CORE-0001 REQ-CORE-0001X'
        matches = ID_PATTERN.findall(text)
        # XREQ-CORE-0001 matches because \b is at string start before X;
        # REQ-CORE-0001X does NOT match because there's no \b between 1 and X
        self.assertEqual(matches, ['XREQ-CORE-0001'])


if __name__ == '__main__':
    unittest.main()
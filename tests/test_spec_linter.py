#!/usr/bin/env python3
"""Unit tests for spec_linter.py."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.spec_linter import (
    find_markdown_files,
    generate_csv,
    generate_report,
    is_definition_file,
    is_heading_line,
    lint_repository,
    validate_format,
    LintResult,
)


class TestValidateFormat(unittest.TestCase):
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


class TestIsHeadingLine(unittest.TestCase):
    def test_heading_level_3_with_id(self):
        self.assertTrue(is_heading_line('### REQ-CORE-0001'))
    def test_heading_level_2(self):
        self.assertTrue(is_heading_line('## Scope'))
    def test_heading_level_1(self):
        self.assertTrue(is_heading_line('# Purpose'))
    def test_prose_not_heading(self):
        self.assertFalse(is_heading_line('Some text with REQ-CORE-0001'))
    def test_list_not_heading(self):
        self.assertFalse(is_heading_line('- REQ-CORE-0001'))
    def test_table_not_heading(self):
        self.assertFalse(is_heading_line('| REQ-CORE-0001 | SPEC.md |'))


class TestIsDefinitionFile(unittest.TestCase):
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
    def test_idscheme_not_definition(self):
        self.assertFalse(is_definition_file('META/SPEC-IDScheme.md'))
    def test_task_file_is_definition(self):
        self.assertTrue(is_definition_file('IMPLEMENTATION/Epic/TASK-CORE-0001.md'))


class TestFindMarkdownFiles(unittest.TestCase):
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

    def test_excludes_generated_files(self):
        (self.tmpdir / 'TRACEABILITY').mkdir()
        (self.tmpdir / 'TRACEABILITY' / 'lint_report.md').touch()
        (self.tmpdir / 'TRACEABILITY' / 'backlog.md').touch()
        (self.tmpdir / 'SPEC.md').touch()
        files = find_markdown_files(self.tmpdir)
        self.assertEqual(len(files), 1)
        self.assertIn(self.tmpdir / 'SPEC.md', files)


class TestLintRepository(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)
    def _write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def test_clean_repository_no_issues(self):
        self._write(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        self._write(self.tmpdir / 'DOMAIN' / 'SPEC-Claim.md', '### REQ-CLAIM-0001\n')
        result = lint_repository(self.tmpdir)
        self.assertEqual(len(result.definitions), 2)
        self.assertEqual(len(result.duplicates), 0)
        self.assertEqual(len(result.invalid_format), 0)
        self.assertEqual(len(result.undefined_refs), 0)
        self.assertFalse(result.has_issues)

    def test_duplicate_ids_detected(self):
        self._write(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        self._write(self.tmpdir / 'SPEC-Other.md', '### REQ-CORE-0001\n')
        result = lint_repository(self.tmpdir)
        self.assertEqual(len(result.duplicates), 1)
        self.assertEqual(result.duplicates[0][0], 'REQ-CORE-0001')

    def test_invalid_format_detected(self):
        self._write(self.tmpdir / 'SPEC.md', '### REQ-core-0001\n')
        result = lint_repository(self.tmpdir)
        self.assertEqual(len(result.invalid_format), 1)

    def test_undefined_references_detected(self):
        # Reference in prose, not a heading
        self._write(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        self._write(self.tmpdir / 'SPEC-Claim.md', 'See also REQ-CORE-9999\n')
        result = lint_repository(self.tmpdir)
        self.assertEqual(len(result.undefined_refs), 1)

    def test_tasks_not_reported_as_undefined(self):
        self._write(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        # Reference to TASK-PROD-0001 should be skipped
        self._write(self.tmpdir / 'SPEC-Claim.md', 'See TASK-PROD-0001\n')
        result = lint_repository(self.tmpdir)
        self.assertEqual(len(result.undefined_refs), 0)

    def test_exclude_dirs_ignored(self):
        self._write(self.tmpdir / '.git' / 'c.md', '### REQ-CORE-0001\n')
        self._write(self.tmpdir / 'SPEC.md', '### REQ-CORE-0002\n')
        result = lint_repository(self.tmpdir)
        self.assertIn('REQ-CORE-0002', result.definitions)
        self.assertNotIn('REQ-CORE-0001', result.definitions)

    def test_empty_repository(self):
        result = lint_repository(self.tmpdir)
        self.assertEqual(len(result.definitions), 0)
        self.assertEqual(result.files_scanned, 0)

    def test_root_spec_included(self):
        self._write(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n### REQ-CORE-0002\n')
        result = lint_repository(self.tmpdir)
        self.assertIn('REQ-CORE-0001', result.definitions)
        self.assertIn('REQ-CORE-0002', result.definitions)

    def test_idscheme_not_scanned_as_definitions(self):
        self._write(self.tmpdir / 'SPEC.md', '### REQ-CORE-0001\n')
        self._write(self.tmpdir / 'META' / 'SPEC-IDScheme.md', '### REQ-CORE-0001\n')
        result = lint_repository(self.tmpdir)
        # Only one definition of REQ-CORE-0001, no duplicate
        self.assertEqual(len(result.duplicates), 0)


class TestGenerateCsv(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_csv_output_format(self):
        result = LintResult()
        result.definitions = {
            'REQ-CORE-0001': [('SPEC.md', 3)],
            'REQ-CLAIM-0001': [('DOMAIN/SPEC-Claim.md', 5)],
        }
        result.files_scanned = 2
        csv_path = self.tmpdir / 'out.csv'
        generate_csv(result, csv_path, self.tmpdir)
        with open(csv_path, newline='', encoding='utf-8') as f:
            rows = list(csv.reader(f))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], ['id', 'source_file', 'type', 'status'])

    def test_csv_undefined_refs_included(self):
        result = LintResult()
        result.definitions = {'REQ-CORE-0001': [('SPEC.md', 3)]}
        result.undefined_refs = [('REQ-CORE-9999', 'SPEC-Claim.md', 10)]
        result.files_scanned = 2
        csv_path = self.tmpdir / 'out.csv'
        generate_csv(result, csv_path, self.tmpdir)
        with open(csv_path, newline='', encoding='utf-8') as f:
            rows = list(csv.reader(f))
        row_ids = [r[0] for r in rows[1:]]
        self.assertIn('REQ-CORE-9999', row_ids)

    def test_csv_with_duplicates(self):
        result = LintResult()
        result.definitions = {'REQ-CORE-0002': [('SPEC.md', 5)]}
        result.duplicates = [('REQ-CORE-0001', [('SPEC.md', 3), ('SPEC-O.md', 7)], 1, 'definition')]
        csv_path = self.tmpdir / 'out.csv'
        generate_csv(result, csv_path, self.tmpdir)
        with open(csv_path, newline='', encoding='utf-8') as f:
            rows = list(csv.reader(f))
        self.assertEqual(len(rows), 3)

    def test_csv_type_inference(self):
        result = LintResult()
        result.definitions = {
            'REQ-CORE-0001': [('SPEC.md', 1)],
            'API-REST-0001': [('API/SPEC-REST.md', 1)],
            'TEST-VAL-0001': [('TESTING/SPEC-Validation.md', 1)],
        }
        csv_path = self.tmpdir / 'out.csv'
        generate_csv(result, csv_path, self.tmpdir)
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            types = {r['id']: r['type'] for r in reader}
        self.assertEqual(types['REQ-CORE-0001'], 'functional')
        self.assertEqual(types['API-REST-0001'], 'api')
        self.assertEqual(types['TEST-VAL-0001'], 'test')


class TestGenerateReport(unittest.TestCase):
    def test_report_no_issues(self):
        result = LintResult()
        result.files_scanned = 5
        result.definitions = {'REQ-CORE-0001': [('SPEC.md', 1)]}
        report = generate_report(result, Path('/repo'))
        self.assertIn('No issues found', report)

    def test_report_with_duplicates(self):
        result = LintResult()
        result.files_scanned = 2
        result.duplicates = [('REQ-CORE-0001', [('SPEC.md', 3), ('SPEC-O.md', 7)], 1, 'definition')]
        report = generate_report(result, Path('/repo'))
        self.assertIn('Duplicate Definitions', report)

    def test_report_with_undefined(self):
        result = LintResult()
        result.files_scanned = 1
        result.undefined_refs = [('REQ-CORE-9999', 'SPEC.md', 5)]
        report = generate_report(result, Path('/repo'))
        self.assertIn('Referenced But Never Defined', report)

    def test_report_with_invalid_format(self):
        result = LintResult()
        result.files_scanned = 1
        result.invalid_format = [('req-core-0001', 'SPEC.md', 3)]
        report = generate_report(result, Path('/repo'))
        self.assertIn('Invalid Format IDs', report)


if __name__ == '__main__':
    unittest.main()
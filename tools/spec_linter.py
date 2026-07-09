#!/usr/bin/env python3
"""
spec_linter.py — Specification ID Linter for ORKP.

Scans Markdown SPEC files, validates ID uniqueness and format compliance,
detects obsolete IDs, and outputs a traceability CSV report.

Usage:
    python tools/spec_linter.py [--path REPO_ROOT] [--output CSV_PATH]

Source requirements:
    - META-ID-0001
    - META-TASK-0001
"""

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Match IDs of format PREFIX-DOMAIN-NNNN, case-insensitive, but NOT inside inline code (backticks)
ID_PATTERN = re.compile(r'(?<!`)\b([A-Z]+-[A-Z]+-\d{4})\b(?!`)', re.IGNORECASE)
DEFAULT_EXCLUDE_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv'}
# Files to exclude entirely from scanning
DEFAULT_EXCLUDE_FILES = {'lint_report.md', 'test_spec_linter.py', 'test_backlog_generator.py'}
CSV_COLUMNS = ['id', 'source_file', 'type', 'status']

# Files that are considered definition sources (not references)
DEFINITION_PATTERNS = (
    'SPEC.md',
    'SPEC-*.md',
    'REQ-*.md',
    'TASK-*.md',
)

# Files that contain example IDs (not definitions)
EXAMPLE_FILES = {
    'SPEC-IDScheme.md',
}


def is_definition_file(filename: str) -> bool:
    """Check if a filename is a definition source (SPEC or TASK file)."""
    basename = Path(filename).name
    if basename in EXAMPLE_FILES:
        return False
    if basename == 'TASK.md':
        return False
    if basename == 'SPEC.md':
        return True
    if basename.startswith('SPEC-') and basename.endswith('.md'):
        return True
    if basename.startswith('REQ-') and basename.endswith('.md'):
        return True
    if basename.startswith('TASK-') and basename.endswith('.md'):
        return True
    return False


def is_definition_line(line: str) -> bool:
    """Check if a line is a definition heading (#, ##, or ### with an ID)."""
    stripped = line.strip()
    return stripped.startswith('### ') or stripped.startswith('## ') or stripped.startswith('# ')


def _infer_type(prefix: str) -> str:
    """Infer requirement type from ID prefix."""
    type_map = {
        'REQ': 'functional',
        'NFR': 'non-functional',
        'DB': 'database',
        'API': 'api',
        'AI': 'ai',
        'WF': 'workflow',
        'REP': 'report',
        'UI': 'ui',
        'SEC': 'security',
        'TEST': 'test',
        'ADR': 'architecture',
        'TASK': 'task',
        'META': 'meta',
    }
    return type_map.get(prefix, 'unknown')


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LintResult:
    """Aggregated results from a linting run."""
    ids_found: Dict[str, List[Tuple[str, int]]] = field(default_factory=lambda: defaultdict(list))
    duplicates: List[Tuple[str, List[Tuple[str, int]], int, str]] = field(default_factory=list)
    invalid_format: List[Tuple[str, str, int]] = field(default_factory=list)
    files_scanned: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def total_ids(self) -> int:
        return len(self.ids_found)

    @property
    def has_issues(self) -> bool:
        return bool(self.duplicates) or bool(self.invalid_format) or bool(self.errors)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def find_markdown_files(root: Path, exclude_dirs: Set[str] = None, exclude_files: Set[str] = None) -> List[Path]:
    """Recursively find all .md files, excluding specified directories and filenames."""
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS
    if exclude_files is None:
        exclude_files = DEFAULT_EXCLUDE_FILES
    md_files = []
    for entry in root.rglob('*.md'):
        # Check if any parent directory is in the exclude list
        if any(part in exclude_dirs for part in entry.relative_to(root).parts):
            continue
        # Check if the filename is excluded
        if entry.name in exclude_files:
            continue
        md_files.append(entry)
    return sorted(md_files)


def extract_ids_from_file(filepath: Path) -> List[Tuple[str, int, bool]]:
    """Extract all requirement IDs from a Markdown file with line numbers and definition flag."""
    results = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_no, line in enumerate(f, 1):
                for match in ID_PATTERN.finditer(line):
                    is_def = is_definition_line(line)
                    results.append((match.group(1), line_no, is_def))
    except (IOError, OSError) as e:
        print(f"  ⚠  Error reading {filepath}: {e}", file=sys.stderr)
    return results


def validate_format(raw_id: str) -> bool:
    """Validate that an ID matches the PREFIX-DOMAIN-NNNN format."""
    return bool(re.match(r'^[A-Z]+-[A-Z]+-\d{4}$', raw_id))


def lint_repository(root: Path, exclude_dirs: Set[str] = None, exclude_files: Set[str] = None) -> LintResult:
    """Run the linter on the repository at `root`."""
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS
    if exclude_files is None:
        exclude_files = DEFAULT_EXCLUDE_FILES

    result = LintResult()
    md_files = find_markdown_files(root, exclude_dirs, exclude_files)
    result.files_scanned = len(md_files)

    # Phase 1: Extract all IDs, classifying each as definition or reference
    definitions: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
    references: Dict[str, List[Tuple[str, int]]] = defaultdict(list)

    for filepath in md_files:
        ids_in_file = extract_ids_from_file(filepath)
        rel_path = str(filepath.relative_to(root))
        is_def_file = is_definition_file(rel_path)

        for raw_id, line_no, is_def_line in ids_in_file:
            # Validate format
            if not validate_format(raw_id):
                result.invalid_format.append((raw_id, rel_path, line_no))
                continue

            # An ID is a definition if BOTH:
            #   - the file is a definition source (SPEC/TASK)
            #   - the line looks like a definition heading
            if is_def_file and is_def_line:
                definitions[raw_id].append((rel_path, line_no))
            else:
                references[raw_id].append((rel_path, line_no))

    # Phase 2: Detect real duplicates (same ID defined in multiple SPEC files)
    for raw_id, occurrences in definitions.items():
        # Check if also referenced (normal cross-reference)
        ref_count = len(references.get(raw_id, []))
        if len(occurrences) > 1:
            result.duplicates.append((raw_id, occurrences, ref_count, 'definition'))
        else:
            result.ids_found[raw_id] = occurrences

    # Phase 3: Check for IDs referenced but never defined
    for raw_id, occurrences in references.items():
        if raw_id not in definitions:
            # Skip TASK- prefixed IDs — they are generated by backlog_generator
            # and may not have individual task files yet
            if raw_id.startswith('TASK-'):
                result.ids_found[raw_id] = occurrences
                continue
            result.ids_found[raw_id] = occurrences
            result.errors.append(
                f"ID {raw_id} is referenced in {occurrences[0][0]}:{occurrences[0][1]} "
                f"but never defined in a SPEC file"
            )

    return result


# ---------------------------------------------------------------------------
# Output generators
# ---------------------------------------------------------------------------

def generate_csv(result: LintResult, output_path: Path, repo_root: Path) -> None:
    """Generate a traceability CSV from lint results."""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)

        # Write all unique IDs (first occurrence)
        for raw_id, occurrences in sorted(result.ids_found.items()):
            source_file = occurrences[0][0]
            prefix = raw_id.split('-')[0]
            req_type = _infer_type(prefix)
            writer.writerow([raw_id, source_file, req_type, 'draft'])

        # Also write duplicates (with first occurrence)
        for raw_id, occurrences, ref_count, dup_type in sorted(result.duplicates):
            source_file = occurrences[0][0]
            prefix = raw_id.split('-')[0]
            req_type = _infer_type(prefix)
            writer.writerow([raw_id, source_file, req_type, 'draft'])


def generate_report(result: LintResult, repo_root: Path) -> str:
    """Generate a human-readable Markdown report."""
    lines = []
    lines.append("# Specification Linter Report")
    lines.append("")
    lines.append(f"- **Repository:** {repo_root}")
    lines.append(f"- **Files scanned:** {result.files_scanned}")
    lines.append(f"- **Unique IDs found:** {result.total_ids}")
    lines.append(f"- **Duplicates:** {len(result.duplicates)}")
    lines.append(f"- **Invalid format:** {len(result.invalid_format)}")
    lines.append("")

    if result.duplicates:
        lines.append("## Duplicate Definitions")
        lines.append("")
        lines.append("The following IDs are defined in multiple SPEC files (real duplicates):")
        lines.append("")
        lines.append("| ID | Occurrences |")
        lines.append("|---|---|")
        for raw_id, occurrences, ref_count, dup_type in sorted(result.duplicates):
            locs = "; ".join(f"{f}:{l}" for f, l in occurrences)
            lines.append(f"| {raw_id} | {locs} |")
        lines.append("")

    if result.errors:
        lines.append("## Referenced But Never Defined")
        lines.append("")
        lines.append("The following IDs are referenced in files but never defined in a SPEC:")
        lines.append("")
        for err in result.errors:
            lines.append(f"- {err}")
        lines.append("")

    if result.invalid_format:
        lines.append("## Invalid Format IDs")
        lines.append("")
        lines.append("| ID | File | Line |")
        lines.append("|---|---|---|")
        for raw_id, filepath, line_no in sorted(result.invalid_format):
            lines.append(f"| {raw_id} | {filepath} | {line_no} |")
        lines.append("")

    if not result.has_issues:
        lines.append("✅ **No issues found — all IDs are valid and unique.**")
        lines.append("")

    lines.append("## ID Summary by Prefix")
    lines.append("")
    lines.append("| Prefix | Count |")
    lines.append("|---|---|")
    prefix_counts: Dict[str, int] = defaultdict(int)
    for raw_id in result.ids_found:
        prefix = raw_id.split('-')[0]
        prefix_counts[prefix] += 1
    for raw_id, occurrences, ref_count, dup_type in result.duplicates:
        prefix = raw_id.split('-')[0]
        prefix_counts[prefix] += 1
    for prefix in sorted(prefix_counts):
        lines.append(f"| {prefix} | {prefix_counts[prefix]} |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ORKP Specification ID Linter — validate requirement IDs in Markdown SPEC files."
    )
    parser.add_argument(
        '--path', '-p',
        type=Path,
        default=Path.cwd(),
        help="Root path of the repository to scan (default: current directory)."
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=None,
        help="Output path for the traceability CSV (default: TRACEABILITY/Requirements.csv relative to --path)."
    )
    parser.add_argument(
        '--report', '-r',
        type=Path,
        default=None,
        help="Output path for the Markdown report (default: stdout)."
    )
    parser.add_argument(
        '--strict', '-s',
        action='store_true',
        help="Exit with non-zero code on any issue (duplicates or invalid format)."
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    repo_root = args.path.resolve()

    if not repo_root.is_dir():
        print(f"Error: {repo_root} is not a valid directory.", file=sys.stderr)
        return 1

    print(f"🔍 Scanning {repo_root} ...")
    result = lint_repository(repo_root)

    print(f"   Files scanned: {result.files_scanned}")
    print(f"   Unique IDs:    {result.total_ids}")
    print(f"   Duplicates:    {len(result.duplicates)}")
    print(f"   Invalid fmt:   {len(result.invalid_format)}")

    # Generate CSV
    output_path = args.output or (repo_root / 'TRACEABILITY' / 'Requirements.csv')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generate_csv(result, output_path, repo_root)
    print(f"   CSV written:   {output_path}")

    # Generate report
    report = generate_report(result, repo_root)
    if args.report:
        args.report.write_text(report, encoding='utf-8')
        print(f"   Report:        {args.report}")
    else:
        print("\n" + report)

    # Exit code
    if result.has_issues and args.strict:
        print("\n❌ Issues found (strict mode).", file=sys.stderr)
        return 1

    print("\n✅ Linter finished.")
    return 0


if __name__ == '__main__':
    sys.exit(main())

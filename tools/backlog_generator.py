#!/usr/bin/env python3
"""
backlog_generator.py — Task Backlog Generator for ORKP.

Reads requirement IDs from Markdown SPEC files (heading definitions only),
groups them by domain (from META/task_groups.json), and generates a
structured task backlog in Markdown and CSV formats with deterministic task IDs.

Usage:
    python tools/backlog_generator.py [--path REPO_ROOT] [--output-dir OUTPUT_DIR]

Source requirements:
    - META-TASK-0001
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ID_PATTERN = re.compile(r'(?<!`)\b([A-Z]+-[A-Z]+-\d{4})\b(?!`)', re.IGNORECASE)
EXCLUDE_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv'}
EXCLUDE_FILES = {
    'lint_report.md', 'backlog.md', 'backlog.csv', 'Requirements.csv',
    'test_spec_linter.py', 'test_backlog_generator.py',
    'README.md', 'GLOSSARY.md', 'ROADMAP.md', 'VISION.md',
}
GENERATED_FILES = {'TASK.md', 'TRACEABILITY/backlog.md', 'TRACEABILITY/backlog.csv', 'TRACEABILITY/Requirements.csv', 'TRACEABILITY/lint_report.md'}

CONFIG_PATH = 'META/task_groups.json'


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(root: Path) -> Dict[str, Any]:
    """Load task group configuration from META/task_groups.json."""
    config_path = root / CONFIG_PATH
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_markdown_files(root: Path) -> List[Path]:
    """Find all .md SPEC files, excluding unwanted dirs and generated files."""
    md_files = []
    for entry in root.rglob('*.md'):
        if any(part in EXCLUDE_DIRS for part in entry.relative_to(root).parts):
            continue
        if entry.name in EXCLUDE_FILES:
            continue
        if entry.name in GENERATED_FILES or str(entry.relative_to(root)) in GENERATED_FILES:
            continue
        # Only include SPEC.md, REQ-*.md, and SPEC-*.md
        if entry.name == 'SPEC.md' or entry.name.startswith('SPEC-') or entry.name.startswith('REQ-'):
            md_files.append(entry)
    return sorted(md_files)


def is_heading_line(line: str) -> bool:
    """Check if a line is a Markdown heading (any level)."""
    stripped = line.strip()
    return stripped.startswith('#')


def extract_requirement_ids(filepath: Path) -> List[str]:
    """
    Extract requirement IDs from heading lines ONLY.
    Returns a sorted unique list of IDs defined in the file.
    """
    seen: set[str] = set()
    results: list[str] = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if is_heading_line(line):
                    for match in ID_PATTERN.finditer(line):
                        raw_id = match.group(1).upper()
                        if raw_id not in seen:
                            seen.add(raw_id)
                            results.append(raw_id)
    except (IOError, OSError) as e:
        print(f"  ⚠  Error reading {filepath}: {e}", file=sys.stderr)
    return results


def is_definition_file(name: str) -> bool:
    """Check if a filename is a definition source (SPEC file, not generated)."""
    basename = Path(name).name
    if basename == 'SPEC-IDScheme.md':
        return False
    if basename == 'TASK.md':
        return False
    if basename == 'SPEC.md':
        return True
    if basename.startswith('SPEC-') and basename.endswith('.md'):
        return True
    if basename.startswith('REQ-') and basename.endswith('.md'):
        return True
    return False


def collect_definitions(root: Path) -> Dict[str, List[str]]:
    """
    Collect all requirement IDs from heading lines of SPEC files.
    Returns {ID: [source_file_rel_path, ...]}.
    """
    definitions: Dict[str, List[str]] = defaultdict(list)
    md_files = find_markdown_files(root)
    for filepath in md_files:
        rel_path = str(filepath.relative_to(root))
        if not is_definition_file(rel_path):
            continue
        ids = extract_requirement_ids(filepath)
        for rid in ids:
            definitions[rid].append(rel_path)
    return definitions


# ---------------------------------------------------------------------------
# Backlog generation
# ---------------------------------------------------------------------------

def generate_backlog(root: Path) -> Tuple[List[Dict], List[Dict]]:
    """Generate task backlog from SPEC files.

    Returns:
        (foundation_tasks, generated_tasks) where each is a list of task dicts.
    """
    config = load_config(root)
    domain_groups = config.get('domain_groups', [])
    foundation_tasks_cfg = config.get('foundation_tasks', [])

    # Collect all requirement definitions from SPEC files
    all_definitions = collect_definitions(root)

    # Build a set of all defined requirement IDs
    all_defined_ids: set[str] = set()
    for rid in all_definitions:
        all_defined_ids.add(rid)

    # Foundation tasks are always included
    foundation_tasks = []
    for ft in foundation_tasks_cfg:
        foundation_tasks.append({
            'task_id': ft['task_id'],
            'title': ft['title'],
            'requirements': list(ft['requirements']),
            'epic': ft['epic'],
            'phase': ft['phase'],
            'scope': ft.get('scope', ''),
        })

    # Collect requirements already covered by foundation tasks
    covered_reqs: set[str] = set()
    for ft in foundation_tasks:
        for r in ft['requirements']:
            covered_reqs.add(r)

    # Group remaining requirement IDs by domain prefix
    remaining_ids = all_defined_ids - covered_reqs
    groups: Dict[str, List[str]] = defaultdict(list)
    for rid in remaining_ids:
        matched = False
        for group in domain_groups:
            if rid.startswith(group['prefix']):
                groups[group['task_suffix']].append(rid)
                matched = True
                break
        if not matched:
            parts = rid.split('-')
            if len(parts) >= 2:
                groups[parts[0]].append(rid)

    # Generate tasks — deterministic IDs (always -0001 per group)
    generated_tasks = []
    for group in domain_groups:
        suffix = group['task_suffix']
        if suffix not in groups:
            continue
        req_ids = sorted(groups[suffix])
        task = {
            'task_id': f'TASK-{suffix}-0001',
            'title': group['title'],
            'requirements': req_ids,
            'epic': group['epic'],
            'phase': group['phase'],
            'scope': group['scope'],
        }
        generated_tasks.append(task)

    return foundation_tasks, generated_tasks


# ---------------------------------------------------------------------------
# Output generators
# ---------------------------------------------------------------------------

def today_str() -> str:
    """Return today's date as ISO string (YYYY-MM-DD)."""
    return date.today().isoformat()


def generate_markdown_backlog(foundation_tasks: List[Dict], generated_tasks: List[Dict], output_path: Path) -> None:
    """Generate a Markdown backlog file."""
    lines = []
    lines.append("# ORKP Task Backlog")
    lines.append("")
    lines.append(f"Generated on {today_str()}")
    lines.append("")
    all_tasks = foundation_tasks + generated_tasks
    lines.append(f"- **Foundation tasks:** {len(foundation_tasks)}")
    lines.append(f"- **Generated tasks:** {len(generated_tasks)}")
    total_reqs = sum(len(t['requirements']) for t in all_tasks)
    lines.append(f"- **Total requirement IDs covered:** {total_reqs}")
    lines.append("")

    epics = defaultdict(list)
    for task in all_tasks:
        epics[task['epic']].append(task)

    for epic_name in sorted(epics.keys()):
        lines.append(f"## {epic_name}")
        lines.append("")
        for task in epics[epic_name]:
            lines.append(f"### {task['task_id']} — {task['title']}")
            lines.append("")
            lines.append("**Source requirements:**")
            for req_id in task['requirements']:
                lines.append(f"- {req_id}")
            lines.append("")
            if task.get('scope'):
                lines.append(f"**Scope:** {task['scope']}")
                lines.append("")
            lines.append(f"**Phase:** {task['phase']}")
            lines.append("")

    output_path.write_text('\n'.join(lines), encoding='utf-8')


def generate_csv_backlog(foundation_tasks: List[Dict], generated_tasks: List[Dict], output_path: Path) -> None:
    """Generate a CSV backlog file."""
    all_tasks = foundation_tasks + generated_tasks
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['task_id', 'title', 'requirement_ids', 'epic', 'phase'])
        for task in all_tasks:
            writer.writerow([
                task['task_id'],
                task['title'],
                '; '.join(task['requirements']),
                task['epic'],
                task['phase'],
            ])


def generate_task_md(foundation_tasks: List[Dict], generated_tasks: List[Dict], output_path: Path) -> None:
    """Generate TASK.md from backlog data with detailed task structure."""
    lines = []
    lines.append("# SWE Batch Plan (Auto-Generated)")
    lines.append("")
    lines.append("> This file is auto-generated from SPEC files by `tools/backlog_generator.py`.")
    lines.append("> Do not edit manually — regenerate with `python tools/backlog_generator.py --task-md`.")
    lines.append("")

    all_tasks = foundation_tasks + generated_tasks
    epics = defaultdict(list)
    for task in all_tasks:
        epics[task['epic']].append(task)

    for epic_name in sorted(epics.keys()):
        lines.append(f"## {epic_name}")
        lines.append("")
        for task in epics[epic_name]:
            lines.append(f"### {task['task_id']}")
            lines.append(f"{task['title']}.")
            lines.append("")
            lines.append("Source requirements:")
            lines.append("")
            for req_id in task['requirements']:
                lines.append(f"- {req_id}")
            lines.append("")
            if task.get('scope'):
                lines.append("Scope:")
                lines.append("")
                for item in task['scope'].split(', '):
                    lines.append(f"- {item}")
                lines.append("")
            lines.append("Acceptance criteria:")
            lines.append("")
            lines.append(f"- {task['title']} implemented and tested.")
            for req_id in task['requirements']:
                lines.append(f"- {req_id} satisfied.")
            lines.append("")

    output_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"   TASK.md:  {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ORKP Task Backlog Generator — generate task stubs from SPEC requirements."
    )
    parser.add_argument(
        '--path', '-p',
        type=Path,
        default=Path.cwd(),
        help="Root path of the repository (default: current directory)."
    )
    parser.add_argument(
        '--output-dir', '-o',
        type=Path,
        default=None,
        help="Output directory for backlog files (default: TRACEABILITY/)."
    )
    parser.add_argument(
        '--task-md', '-t',
        action='store_true',
        help="Also generate TASK.md in the repository root."
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    repo_root = args.path.resolve()

    if not repo_root.is_dir():
        print(f"Error: {repo_root} is not a valid directory.", file=sys.stderr)
        return 1

    output_dir = args.output_dir or (repo_root / 'TRACEABILITY')
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📋 Generating backlog from {repo_root} ...")
    foundation_tasks, generated_tasks = generate_backlog(repo_root)

    print(f"   Foundation tasks: {len(foundation_tasks)}")
    print(f"   Generated tasks:  {len(generated_tasks)}")

    md_path = output_dir / 'backlog.md'
    csv_path = output_dir / 'backlog.csv'

    generate_markdown_backlog(foundation_tasks, generated_tasks, md_path)
    print(f"   Markdown: {md_path}")

    generate_csv_backlog(foundation_tasks, generated_tasks, csv_path)
    print(f"   CSV:      {csv_path}")

    if args.task_md:
        task_md_path = repo_root / 'TASK.md'
        generate_task_md(foundation_tasks, generated_tasks, task_md_path)

    print(f"\n✅ Backlog generated.")
    return 0


if __name__ == '__main__':
    sys.exit(main())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ORKP Task Backlog Generator — generate task stubs from SPEC requirements."
    )
    parser.add_argument(
        '--path', '-p',
        type=Path,
        default=Path.cwd(),
        help="Root path of the repository (default: current directory)."
    )
    parser.add_argument(
        '--output-dir', '-o',
        type=Path,
        default=None,
        help="Output directory for backlog files (default: TRACEABILITY/)."
    )
    parser.add_argument(
        '--task-md', '-t',
        action='store_true',
        help="Also generate TASK.md in the repository root."
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    repo_root = args.path.resolve()

    if not repo_root.is_dir():
        print(f"Error: {repo_root} is not a valid directory.", file=sys.stderr)
        return 1

    output_dir = args.output_dir or (repo_root / 'TRACEABILITY')
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📋 Generating backlog from {repo_root} ...")
    existing_tasks, generated_tasks = generate_backlog(repo_root)

    print(f"   Existing tasks: {len(existing_tasks)}")
    print(f"   Generated tasks: {len(generated_tasks)}")

    # Write outputs
    md_path = output_dir / 'backlog.md'
    csv_path = output_dir / 'backlog.csv'

    generate_markdown_backlog(existing_tasks, generated_tasks, md_path)
    print(f"   Markdown: {md_path}")

    generate_csv_backlog(existing_tasks, generated_tasks, csv_path)
    print(f"   CSV:      {csv_path}")

    if args.task_md:
        task_md_path = repo_root / 'TASK.md'
        generate_task_md(existing_tasks, generated_tasks, task_md_path)

    print(f"\n✅ Backlog generated.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
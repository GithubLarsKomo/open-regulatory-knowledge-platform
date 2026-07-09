#!/usr/bin/env python3
"""
backlog_generator.py — Task Backlog Generator for ORKP.

Reads requirement IDs from Markdown SPEC files, groups them by domain,
and generates a structured task backlog in Markdown and CSV formats.

Usage:
    python tools/backlog_generator.py [--path REPO_ROOT] [--output-dir OUTPUT_DIR]

Source requirements:
    - META-TASK-0001
"""

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ID_PATTERN = re.compile(r'(?<!`)\b([A-Z]+-[A-Z]+-\d{4})\b(?!`)', re.IGNORECASE)
EXCLUDE_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv'}
EXCLUDE_FILES = {'lint_report.md', 'test_spec_linter.py', 'test_backlog_generator.py', 'README.md', 'GLOSSARY.md', 'ROADMAP.md', 'VISION.md', 'SPEC.md', 'TASK.md'}

# Requirements that already have task files (skip these)
EXISTING_TASK_REQUIREMENTS = {
    'META-ID-0001',
    'META-TASK-0001',
    'REQ-CORE-0001',
    'REQ-ARCH-0001',
    'DB-CORE-0001',
    'DB-CORE-0002',
    'DB-CORE-0005',
    'API-REST-0001',
    'API-REST-0004',
}

# Domain grouping rules: map requirement prefixes to domains/tasks
DOMAIN_GROUPS = [
    {
        'prefix': 'REQ-CORE',
        'task_suffix': 'CORE',
        'title': 'Core Platform',
        'epic': 'Epic 002 — Core Object Store',
        'phase': '1',
        'scope': 'Core object model, versioning, event store, audit trail, baseline.',
    },
    {
        'prefix': 'REQ-ARCH',
        'task_suffix': 'ARCH',
        'title': 'Architecture',
        'epic': 'Epic 002 — Core Object Store',
        'phase': '1',
        'scope': 'Architecture enforcement, multi-representation support.',
    },
    {
        'prefix': 'DB-CORE',
        'task_suffix': 'DB',
        'title': 'Database Schema',
        'epic': 'Epic 002 — Core Object Store',
        'phase': '1',
        'scope': 'MariaDB schema, migrations, indexing.',
    },
    {
        'prefix': 'REQ-PROD',
        'task_suffix': 'PROD',
        'title': 'Product Domain',
        'epic': 'Epic 004 — Product & Claim Domain',
        'phase': '2',
        'scope': 'Product master data, device hierarchy, regulatory identifiers.',
    },
    {
        'prefix': 'REQ-CLAIM',
        'task_suffix': 'CLAIM',
        'title': 'Claim Domain',
        'epic': 'Epic 004 — Product & Claim Domain',
        'phase': '2',
        'scope': 'Claim management, evidence linking, consistency checking.',
    },
    {
        'prefix': 'REQ-EVID',
        'task_suffix': 'EVID',
        'title': 'Evidence Domain',
        'epic': 'Epic 004 — Product & Claim Domain',
        'phase': '2',
        'scope': 'Evidence management, quality assessment, coverage analysis.',
    },
    {
        'prefix': 'REQ-RISK',
        'task_suffix': 'RISK',
        'title': 'Risk Domain',
        'epic': 'Epic 005 — Risk Domain',
        'phase': '2',
        'scope': 'Risk management per ISO 14971, control measures, residual risk.',
    },
    {
        'prefix': 'REQ-PERF',
        'task_suffix': 'PERF',
        'title': 'Performance Domain',
        'epic': 'Epic 006 — Performance Domain',
        'phase': '2',
        'scope': 'Performance studies, analytical/clinical performance, PER.',
    },
    {
        'prefix': 'REP-PER',
        'task_suffix': 'REPORT',
        'title': 'Report Generation',
        'epic': 'Epic 007 — Report Generation MVP',
        'phase': '3',
        'scope': 'DOCX/PDF generation, PER generation, traceability appendix.',
    },
    {
        'prefix': 'GRAPH-CORE',
        'task_suffix': 'GRAPH',
        'title': 'Knowledge Graph',
        'epic': 'Epic 008 — Knowledge Graph',
        'phase': '4',
        'scope': 'Neo4j schema, synchronization, impact analysis.',
    },
    {
        'prefix': 'AI-CORE',
        'task_suffix': 'AI',
        'title': 'AI/RAG Services',
        'epic': 'Epic 009 — AI/RAG Services',
        'phase': '5',
        'scope': 'Hybrid search, grounded drafting, audit trail.',
    },
    {
        'prefix': 'WF-APP',
        'task_suffix': 'WF',
        'title': 'Workflow & Approval',
        'epic': 'Epic 010 — Workflow & Security',
        'phase': '2',
        'scope': 'Lifecycle state machine, approval workflow, electronic signatures.',
    },
    {
        'prefix': 'SEC-RBAC',
        'task_suffix': 'SEC',
        'title': 'Security & RBAC',
        'epic': 'Epic 010 — Workflow & Security',
        'phase': '2',
        'scope': 'Role-based access control, product permissions, audit access.',
    },
    {
        'prefix': 'REQ-UI',
        'task_suffix': 'UI',
        'title': 'User Interface',
        'epic': 'Epic 011 — UI',
        'phase': '3',
        'scope': 'Dashboard, search, editing, workflow UI, AI drafting interface.',
    },
    {
        'prefix': 'TEST-VAL',
        'task_suffix': 'VAL',
        'title': 'Validation & Testing',
        'epic': 'Epic 012 — Validation & Deployment',
        'phase': '6',
        'scope': 'Validation plan, requirement-to-test traceability, audit testing.',
    },
]

# Specific requirements mapped to multi-requirement tasks
EXISTING_TASKS = {
    'TASK-FOUNDATION-0001': {
        'title': 'Create Repository Skeleton',
        'requirements': ['REQ-CORE-0001', 'REQ-ARCH-0001'],
        'epic': 'Epic 001 — Specification Foundation',
        'phase': '0',
    },
    'TASK-FOUNDATION-0002': {
        'title': 'Implement Specification ID Linter',
        'requirements': ['META-ID-0001', 'META-TASK-0001'],
        'epic': 'Epic 001 — Specification Foundation',
        'phase': '0',
    },
    'TASK-FOUNDATION-0003': {
        'title': 'Generate Initial Task Backlog from SPEC Files',
        'requirements': ['META-TASK-0001'],
        'epic': 'Epic 001 — Specification Foundation',
        'phase': '0',
    },
}


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def find_markdown_files(root: Path) -> List[Path]:
    """Find all .md SPEC files, excluding unwanted dirs and files."""
    md_files = []
    for entry in root.rglob('*.md'):
        if any(part in EXCLUDE_DIRS for part in entry.relative_to(root).parts):
            continue
        if entry.name in EXCLUDE_FILES:
            continue
        # Only include SPEC files and DOMAIN files
        if entry.name == 'SPEC.md' or entry.name.startswith('SPEC-') or entry.name.startswith('REQ-'):
            md_files.append(entry)
    return sorted(md_files)


def extract_requirements(filepath: Path) -> List[Tuple[str, int]]:
    """Extract requirement IDs from a file, returning (id, line_no)."""
    results = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_no, line in enumerate(f, 1):
                for match in ID_PATTERN.finditer(line):
                    raw_id = match.group(1).upper()
                    results.append((raw_id, line_no))
    except (IOError, OSError) as e:
        print(f"  ⚠  Error reading {filepath}: {e}", file=sys.stderr)
    return results


def group_requirements_by_domain(requirements: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Group requirements by domain prefix."""
    groups = defaultdict(list)
    for req_id, sources in requirements.items():
        # Find the matching domain group
        matched = False
        for group in DOMAIN_GROUPS:
            if req_id.startswith(group['prefix']):
                groups[group['task_suffix']].append(req_id)
                matched = True
                break
        if not matched:
            # Try prefix-based grouping (first 2 parts)
            parts = req_id.split('-')
            if len(parts) >= 2:
                groups[parts[0]].append(req_id)
            else:
                groups['OTHER'].append(req_id)
    return groups


def generate_backlog(root: Path) -> Tuple[List[Dict], List[Dict]]:
    """Generate task backlog from SPEC files.

    Returns:
        (existing_tasks, generated_tasks) where each is a list of task dicts.
    """
    # Collect all requirements from SPEC files
    all_requirements: Dict[str, List[str]] = defaultdict(list)
    md_files = find_markdown_files(root)
    for filepath in md_files:
        rel_path = str(filepath.relative_to(root))
        for req_id, line_no in extract_requirements(filepath):
            if req_id not in EXISTING_TASK_REQUIREMENTS:
                all_requirements[req_id].append(rel_path)

    # Group by domain
    groups = group_requirements_by_domain(all_requirements)

    # Generate tasks from groups
    generated_tasks = []
    task_counter = 1

    for group in DOMAIN_GROUPS:
        suffix = group['task_suffix']
        if suffix not in groups:
            continue

        req_ids = sorted(groups[suffix])
        # Filter out requirements already covered by existing tasks
        req_ids = [r for r in req_ids if r not in EXISTING_TASK_REQUIREMENTS]
        if not req_ids:
            continue

        task = {
            'task_id': f'TASK-{suffix}-{task_counter:04d}',
            'title': group['title'],
            'requirements': req_ids,
            'epic': group['epic'],
            'phase': group['phase'],
            'scope': group['scope'],
        }
        generated_tasks.append(task)
        task_counter += 1

    # Build existing tasks list
    existing_tasks = []
    for task_id, info in EXISTING_TASKS.items():
        existing_tasks.append({
            'task_id': task_id,
            'title': info['title'],
            'requirements': info['requirements'],
            'epic': info['epic'],
            'phase': info['phase'],
            'scope': '',
        })

    return existing_tasks, generated_tasks


# ---------------------------------------------------------------------------
# Output generators
# ---------------------------------------------------------------------------

def generate_markdown_backlog(existing_tasks: List[Dict], generated_tasks: List[Dict], output_path: Path) -> None:
    """Generate a Markdown backlog file."""
    lines = []
    lines.append("# ORKP Task Backlog")
    lines.append("")
    lines.append(f"Generated on 2026-07-07")
    lines.append("")
    lines.append(f"- **Existing tasks:** {len(existing_tasks)}")
    lines.append(f"- **Generated tasks:** {len(generated_tasks)}")
    lines.append(f"- **Total requirement IDs covered:** {sum(len(t['requirements']) for t in generated_tasks) + sum(len(t['requirements']) for t in existing_tasks)}")
    lines.append("")

    # Group by epic
    epics = defaultdict(list)
    for task in existing_tasks + generated_tasks:
        epics[task['epic']].append(task)

    for epic_name in sorted(epics.keys()):
        lines.append(f"## {epic_name}")
        lines.append("")
        for task in epics[epic_name]:
            lines.append(f"### {task['task_id']} — {task['title']}")
            lines.append("")
            lines.append(f"**Source requirements:**")
            for req_id in task['requirements']:
                lines.append(f"- {req_id}")
            lines.append("")
            if task['scope']:
                lines.append(f"**Scope:** {task['scope']}")
                lines.append("")
            lines.append(f"**Phase:** {task['phase']}")
            lines.append("")

    output_path.write_text('\n'.join(lines), encoding='utf-8')


def generate_csv_backlog(existing_tasks: List[Dict], generated_tasks: List[Dict], output_path: Path) -> None:
    """Generate a CSV backlog file."""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['task_id', 'title', 'requirement_ids', 'epic', 'phase'])
        for task in existing_tasks + generated_tasks:
            writer.writerow([
                task['task_id'],
                task['title'],
                '; '.join(task['requirements']),
                task['epic'],
                task['phase'],
            ])


def generate_task_md(existing_tasks: List[Dict], generated_tasks: List[Dict], output_path: Path) -> None:
    """Generate TASK.md from backlog data with detailed task structure."""
    lines = []
    lines.append("# SWE Batch Plan (Auto-Generated)")
    lines.append("")
    lines.append("> This file is auto-generated from SPEC files by `tools/backlog_generator.py`.")
    lines.append("> Do not edit manually — regenerate with `python tools/backlog_generator.py --task-md`.")
    lines.append("")

    # Group by epic
    epics = defaultdict(list)
    for task in existing_tasks + generated_tasks:
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
                lines.append(f"Scope:")
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
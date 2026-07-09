# SPEC-IDScheme.md

## Purpose

This file defines the mandatory identifier scheme for all specifications, requirements, tasks and tests.

## ID Prefixes

| Prefix | Meaning |
|---|---|
| REQ | Functional requirement |
| NFR | Non-functional requirement |
| DB | Database requirement |
| API | API requirement |
| AI | AI requirement |
| WF | Workflow requirement |
| REP | Report requirement |
| UI | UI requirement |
| SEC | Security requirement |
| TEST | Test requirement |
| ADR | Architecture decision |
| TASK | Implementation task |

## Format

`PREFIX-DOMAIN-NNNN`

Examples:

- REQ-RISK-0001
- DB-CORE-0001
- API-REST-0001
- TASK-FOUNDATION-0001

## Rules

1. IDs are immutable.
2. Deleted requirements are marked obsolete, never reused.
3. Each task references at least one requirement ID.
4. Each test references at least one requirement ID.
5. Each code commit should reference one or more task IDs.

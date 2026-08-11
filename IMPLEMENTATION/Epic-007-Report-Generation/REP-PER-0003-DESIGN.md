# REP-PER-0003 — Content Provenance Design

## Goal

Distinguish source-approved report text from AI-generated draft text without embedding an AI engine into Epic 007 and without weakening baseline reproducibility.

## Boundary

AI-generated text is never passed transiently to PER generation. External AI output is accepted only while creating a derived PER Report baseline. The service persists each AI block as a strict draft `report_content` RegulatoryObject and freezes its exact version together with all items from the source Performance Evaluation baseline.

PER generation then remains baseline-only.

## Provenance classes

- `approved_source` — text already contained in an approved frozen Performance Result, currently the exact `interpretation` field when present.
- `ai_draft` — externally generated text persisted as draft `report_content`; never treated as approved.

Each output content block carries an explicit review state:

- `source_approved` for `approved_source` blocks.
- `unapproved_draft` for `ai_draft` blocks.

## AI draft input contract

Each external AI block contains:

- stable `block_id`
- target Performance section
- non-empty text
- non-empty `model_id`
- one or more exact source references

Every source reference must already exist in the source Performance Evaluation baseline. Duplicate block IDs are rejected.

## Derived report baseline

Creating a PER Report baseline:

1. validates the source Performance Evaluation baseline through the side-effect-free Performance report builder;
2. validates every AI draft source reference against exact frozen source items;
3. creates strict draft `report_content` objects;
4. creates a new immutable baseline containing the original exact object versions plus the exact new `report_content` versions;
5. commits atomically.

Later edits or new versions of either regulatory source objects or `report_content` objects cannot change report generation from the frozen derived baseline.

## Non-scope

- invoking an AI model
- AI prompt management
- human approval of AI draft text
- report lifecycle/signature workflow
- DOCX/PDF rendering

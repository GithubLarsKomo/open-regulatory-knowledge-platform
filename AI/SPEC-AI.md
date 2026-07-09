# SPEC-AI.md

## Purpose

Define AI functionality for the platform.

## AI Principles

1. AI shall assist, not approve.
2. AI output shall be grounded in retrieved evidence.
3. AI output shall be traceable to source objects.
4. AI confidence shall be visible to users.
5. AI-generated text shall remain draft until human approval.

## AI Functions

- Draft regulatory report sections
- Summarize literature
- Propose claim wording
- Identify missing evidence
- Detect inconsistencies
- Suggest risk justifications
- Generate review checklists
- Support impact analysis

## Requirements

### AI-CORE-0001
The AI engine shall only generate approved content through a human review workflow.

### AI-CORE-0002
The AI engine shall cite source objects used for generated text.

### AI-CORE-0003
The AI engine shall distinguish between retrieved facts, inferred statements and generated wording.

### AI-CORE-0004
The AI engine shall store prompts, context references and generated draft versions for auditability.

### AI-CORE-0005
The AI engine shall support hybrid retrieval using keyword search, vector search and graph traversal.

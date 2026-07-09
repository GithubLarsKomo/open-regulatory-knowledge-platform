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

## Stakeholders

- Regulatory Authors — use AI drafting assistance
- QM Reviewers — review AI-generated draft content
- System Administrators — configure AI models and retrieval sources

## Domain Model

### AI Session

| Concept | Description |
|---|---|
| Prompt | User input submitted to the AI engine |
| Context | Source objects retrieved as grounding |
| Draft | AI-generated output, stored as draft version |
| Citation | Reference to source object used in generation |
| Confidence | Numeric or qualitative confidence indicator |

### Retrieval Sources

- Object store (regulatory objects, versions)
- Knowledge graph (relationships, impact paths)
- Vector index (semantic similarity search)
- Literature database (external references)

## Interfaces

- REST API — AI drafting requests and responses
- Object Store — source object retrieval
- Knowledge Graph — relationship context
- Vector Index — semantic search
- Report Engine — AI-assisted report section generation

## Data Model

| Field | Type | Description |
|---|---|---|
| session_uuid | UUID | Stable identifier |
| prompt_text | TEXT | Original user prompt |
| context_refs | JSON | Source object references |
| draft_text | TEXT | Generated draft content |
| confidence_score | FLOAT | Confidence indicator |
| lifecycle_state | VARCHAR | draft / reviewed / accepted |
| created_at | DATETIME | Creation timestamp |
| created_by | VARCHAR | User who initiated |

## Workflow

- AI drafting: user prompt → retrieval → generation → draft stored → human review → accept/reject
- AI-generated drafts require human approval before becoming approved regulatory content (WF-APP-0006)
- Prompts and drafts are retained for auditability

## Security

- AI access requires authenticated user with appropriate role
- AI cannot bypass approval workflows
- AI cannot modify approved content
- AI audit trail is read-only

## Acceptance Criteria

- AI can generate a draft report section with source citations.
- AI confidence is displayed alongside generated text.
- A human can accept or reject AI-generated draft.
- Prompts and drafts are stored in the audit log.

## Open Questions

- Which LLM provider(s) to support initially?
- Should AI functions be extensible via plugin architecture?
- How to handle multi-language prompt and generation?

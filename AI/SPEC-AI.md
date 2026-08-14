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

Risk-specific AI drafting shall use the Risk-domain contract in `src/orkp/domain/risk_ai_policy.py`. That contract permits only non-decisional support text such as rationale, assumptions, uncertainty, benefits, residual-risk narrative, considerations, notes and review-checklist text. It rejects acceptability, Benefit-Risk conclusions, risk-estimation fields, control-verification decisions and lifecycle/approval fields.

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

## Grounded AI Draft Record

Before provider-specific generation is introduced, ORKP defines a provider-neutral persistence boundary for AI output.

The governed AI draft object uses Core `object_type = ai_draft` and schema `ai-draft-1.0`.

Every persisted AI draft shall contain:

- the exact original `prompt_text`;
- `model_id` identifying the generating model/provider configuration supplied by the caller;
- exact versioned `context_refs` using stable object UUID + object version;
- one or more classified content blocks;
- a visible `confidence_score` in the range 0..1;
- `initiated_by_user_id`;
- immutable historical Object Store versions after regeneration.

Each content block shall declare exactly one statement kind:

- `retrieved_fact` — wording presented as directly retrieved from cited context;
- `inference` — a derived statement that is not represented as a directly retrieved fact;
- `generated_wording` — proposed regulatory prose generated from cited context.

Every content block shall cite one or more exact source references, and those citations shall be a subset of the frozen `context_refs`. Ungrounded generated regulatory wording is not accepted by this baseline contract.

AI drafts explicitly persist:

- `regulatory_status = unapproved_draft`;
- `approval_authority = human_workflow`;
- `ai_may_approve = false`.

The AI service exposes no approval transition. Human accept/reject/approval integration belongs to `WF-APP-0006` in Epic 010. Until that workflow takes ownership, AI draft objects remain in Core lifecycle state `draft`.

Generic Core creation, generic version creation and generic lifecycle progression for `ai_draft` are blocked so the strict AI persistence contract cannot be bypassed.

An AI draft shall not use another `ai_draft` object as a grounding source. This prevents generated text from being silently laundered into a later draft as if it were retrieved regulatory evidence.

Risk-targeted structured support content is additionally validated by `risk_ai_policy.py` before persistence. Decision fields remain forbidden.

Provider invocation is not part of the grounded persistence boundary. An external/provider result may be submitted to the boundary only after it satisfies the strict grounding/provenance model.

## Interfaces

- REST API — AI drafting requests and responses
- Object Store — source object retrieval and AI draft version/audit persistence
- Knowledge Graph — relationship context
- Vector Index — semantic search
- Report Engine — AI-assisted report section generation
- Risk Domain — validates Risk AI draft content against the non-decision contract before any future AI integration can hand content to Risk workflows

Governed AI draft endpoints:

- `POST /api/v1/ai/drafts`
- `GET /api/v1/ai/drafts/{draft_uuid}`
- `POST /api/v1/ai/drafts/{draft_uuid}/regenerate`

## Data Model

| Field | Type | Description |
|---|---|---|
| session_uuid | UUID | Stable identifier |
| prompt_text | TEXT | Original user prompt |
| context_refs | JSON | Exact source object UUID/version references |
| draft_text | TEXT / structured blocks | Generated draft content with statement classification and citations |
| confidence_score | FLOAT | Confidence indicator |
| lifecycle_state | VARCHAR | AI persistence boundary remains draft until human workflow |
| created_at | DATETIME | Creation timestamp |
| created_by | VARCHAR | User who initiated or regenerated |

## Workflow

- AI drafting: user prompt → retrieval → generation → strict grounded draft persistence → human review → accept/reject
- AI-generated drafts require human approval before becoming approved regulatory content (WF-APP-0006)
- AI persistence itself never marks generated content approved
- Risk AI drafting: generated support text → `risk_ai_policy` validation → draft-only content → human Risk workflow
- Prompts, exact context references and every generated draft version are retained through the Object Store/event audit trail

## Security

- AI access requires authenticated user with appropriate role
- AI cannot bypass approval workflows
- AI cannot modify approved content
- AI audit trail is read-only from the AI service perspective
- Generic Core write endpoints cannot create/version/approve `ai_draft` outside the AI domain contract
- AI must not set Risk acceptability, Benefit-Risk conclusions, Risk estimation, verification decisions or lifecycle/approval state; `risk_ai_policy.py` rejects those fields before Risk-domain use (REQ-RISK-0025)
- Trusted identity and role enforcement remain the responsibility of the RBAC/authentication layer; the Risk AI policy is a domain-content boundary, not an authentication substitute

## Acceptance Criteria

- AI can persist a draft report/content section with exact source citations.
- AI confidence is displayed alongside generated text.
- Retrieved facts, inference and generated wording are explicitly distinguishable.
- Prompts, exact context references and generated draft versions are stored for auditability.
- AI persistence cannot mark content approved; human accept/reject is provided by the later workflow layer.
- Risk-specific AI output is limited to non-decisional draft text and cannot contain Risk decision fields.

## Open Questions

- Which LLM provider(s) to support initially?
- Should AI functions be extensible via plugin architecture?
- How to handle multi-language prompt and generation?

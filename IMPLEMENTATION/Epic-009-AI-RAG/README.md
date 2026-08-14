# Epic 009 — AI/RAG Services

## Status

In progress.

## Slice 1 — Auditable Grounded AI Draft Record

Issue: #32

Primary requirements:

- `AI-CORE-0001` — AI output cannot become approved regulatory content without human workflow
- `AI-CORE-0002` — generated text cites exact source objects
- `AI-CORE-0003` — retrieved facts, inference and generated wording are explicit
- `AI-CORE-0004` — prompt/context/generated draft versions are auditable

### Boundary

This slice intentionally does not invoke an LLM provider. It defines the governed persistence boundary that any future provider must satisfy.

AI output is persisted as Core `object_type='ai_draft'` with schema `ai-draft-1.0`.

The Object Store/Event Store provide stable identity, immutable historical versions and audit events. AI does not receive lifecycle or approval authority.

### Grounding contract

Every AI draft freezes:

- original prompt
- model identifier
- exact context UUID/version references
- confidence score
- initiator
- one or more classified content blocks

Content block kinds:

- `retrieved_fact`
- `inference`
- `generated_wording`

Each block requires one or more exact source references, and every cited source must be part of the frozen context set.

AI-generated wording without grounding is rejected.

An `ai_draft` cannot be used as a grounding source for another AI draft. Generated content therefore cannot be silently recycled as if it were retrieved evidence.

### Draft-only governance

Persisted AI payloads declare:

- `regulatory_status='unapproved_draft'`
- `approval_authority='human_workflow'`
- `ai_may_approve=false`

Generic Core creation/versioning for `ai_draft` is blocked. Generic progression to non-draft lifecycle states is blocked. The AI service itself exposes no approval method.

Human accept/reject/approval is deferred to Epic 010 / `WF-APP-0006`.

### Version history

Regeneration while the AI draft remains mutable creates a new Object Store version under the same stable AI draft UUID. Previous prompt, context and generated content remain available through Core version history.

### Risk boundary

For `target_domain='risk'`, optional structured `risk_support` is passed through the existing `risk_ai_policy` validator before persistence.

Risk acceptability, Benefit-Risk conclusions, risk-estimation fields, verification decisions and lifecycle/approval fields remain forbidden.

### REST API

- `POST /api/v1/ai/drafts`
- `GET /api/v1/ai/drafts/{draft_uuid}`
- `POST /api/v1/ai/drafts/{draft_uuid}/regenerate`

## Deferred slice

`AI-CORE-0005` hybrid retrieval is the next Epic-009 slice. It will combine keyword, vector and graph retrieval into the exact context-reference contract established here.

Provider-specific LLM invocation, human workflow integration and RBAC are also deferred.

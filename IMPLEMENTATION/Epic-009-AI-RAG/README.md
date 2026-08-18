# Epic 009 — AI/RAG Services

## Status

In progress.

## Slice 1 — Auditable Grounded AI Draft Record

Issue: #32 — completed.

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

Regeneration while the AI draft remains mutable creates a new Object Store version under the same stable AI draft UUID. Previous prompt, context and generated content remain available through Core version history and the append-only Event Store.

### Risk boundary

For `target_domain='risk'`, free-form blocks may contain only directly cited `retrieved_fact` content. AI-derived Risk `inference` or `generated_wording` blocks are rejected.

Any AI-derived Risk support prose must be supplied through structured `risk_support`, which is passed through the existing `risk_ai_policy` validator before persistence.

Risk acceptability, Benefit-Risk conclusions, risk-estimation fields, verification decisions and lifecycle/approval fields remain forbidden. This prevents free-text AI output from bypassing the Risk-domain non-decision contract.

### REST API

- `POST /api/v1/ai/drafts`
- `GET /api/v1/ai/drafts/{draft_uuid}`
- `POST /api/v1/ai/drafts/{draft_uuid}/regenerate`

## Slice 2 — Deterministic Hybrid Retrieval Contract

Issue: #33.

Primary requirement:

- `AI-CORE-0005` — hybrid retrieval combines keyword search, vector search and graph traversal.

### Retrieval architecture

Hybrid retrieval is exact-version-first. Every channel produces `RetrievalHit` values containing an ORKP object UUID, object version, object type, normalized score and channel identifier.

Channels:

- **keyword** — `ObjectStoreKeywordRetrievalAdapter` searches current Object Store payloads deterministically;
- **vector** — `VectorRetrievalAdapter` is an injected provider-neutral protocol; no vector database or embedding model is hidden in Core;
- **graph** — `GraphRetrievalAdapter` uses the canonical exact-version `GraphProjectionService` from explicit seed references.

The hybrid service revalidates every returned UUID/version against the authoritative Object Store before a hit can become grounding context.

### Fusion

Duplicate hits are merged by exact `(object_uuid, object_version)` identity.

Default channel weights:

- keyword: 0.35
- vector: 0.45
- graph: 0.20

Each candidate exposes all individual channel scores plus the deterministic weighted fused score. Ties are resolved stably by object type, UUID and version.

Historical and current versions are never silently conflated.

### AI grounding boundary

`ai_draft` objects are excluded from keyword, vector and graph results. An `ai_draft` is also rejected as a graph retrieval seed. Generated AI content therefore cannot be laundered into a later draft through retrieval.

Retrieval is read-only and does not change Object Store versions, graph relations, lifecycle or approval state.

### Runtime boundary

No REST retrieval endpoint is exposed in this slice because Core does not yet have a configured vector provider. The domain contract can be used by a later provider/runtime once a concrete `VectorRetrievalAdapter` is injected.

Provider-specific vector stores, embedding models, literature adapters and LLM invocation remain outside this slice.

## Deferred

Provider-specific LLM invocation, concrete vector infrastructure, literature retrieval, human workflow integration and RBAC are deferred to later slices/epics.

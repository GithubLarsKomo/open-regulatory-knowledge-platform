# Epic 010 — Workflow & Security

## Scope

Epic 010 implements the generated backlog tasks:

- `TASK-WF-0001` — workflow and approval;
- `TASK-SEC-0001` — security and RBAC.

The workflow implementation must preserve the existing versioned Object Store,
lifecycle state machine, immutable approved versions, domain-governed approval
gates, and append-only audit trail.

## Slice 1 — Approval decision history and rejection rationale

Tracked by GitHub issue #44.

Requirements addressed:

- `WF-APP-0002` — persisted identified approver, exact object version, decision and timestamp;
- `WF-APP-0003` — rejected objects retain mandatory reviewer comments.

Implementation contract:

1. `StateTransitionRequest` rejects `new_state="rejected"` unless `comments`
   contains non-whitespace reviewer rationale. Validation happens before any
   repository mutation.
2. Existing `ApprovalRecord` persistence remains authoritative for approved and
   rejected lifecycle decisions.
3. `WorkflowService` is a read-only audit query over persisted approval records.
4. `GET /api/v1/objects/{object_uuid}/approvals` exposes exact object version,
   decision, identified actor, decision timestamp, comments and currently stored
   optional signature data.
5. Ordering is deterministic (`decision_timestamp`, then `approval_uuid`). No
   workflow state or approval data is modified by the query.
6. Existing domain-specific approval gates remain unchanged.

Deferred from this slice:

- `WF-APP-0005` cryptographically verifiable electronic-signature/hash contract;
- `SEC-RBAC-*` authorization and role separation;
- parallel/multi-reviewer workflows and escalation.

# SPEC-Claim.md

## Purpose

Define the claim domain as the central hub for regulatory, clinical, analytical, performance, safety and marketing-relevant statements.

## Scope

The domain covers:

- Claim creation, versioning and lifecycle management
- Claim types: regulatory, clinical, analytical, performance, safety, marketing, manufacturing, software
- Evidence linking and coverage evaluation
- Claim approval with evidence gate
- Consistency checking across approved claims
- Report integration (PER, IFU, SSP)
- Multi-language claim support
- Claim history and audit trail

## Stakeholders

- Regulatory Affairs — define and maintain regulatory claims
- Clinical Evidence Reviewer — assess evidence support
- Marketing — define marketing claims
- Quality Management — review and approve claims
- Product Management — own claim portfolio

## Architecture

Claims are stored as `RegulatoryObject` with `object_type='claim'`.
The payload schema is defined in `ClaimPayload` (Pydantic, `extra='forbid'`).

Claims shall never contain embedded evidence. Evidence is always linked via `ObjectRelation`.

```text
Evidence --supported_by--> Claim
Claim --has_claim--> Product
```

## Lifecycle

```text
draft -> in_review -> approved -> effective -> obsolete
    ^         |
    +-- rejected
```

## Workflow

1. Author creates a draft claim with type, category, jurisdiction, language and wording.
2. Author links evidence via `supported_by` relation.
3. Author submits for review -> in_review.
4. Evidence coverage check verifies at least one approved evidence relation exists.
5. If coverage fails -> approval blocked.
6. Reviewer approves or rejects.
7. Approved claims are reusable across reports.

## Relationships

| Relation | Source | Target | Description |
|---|---|---|---|
| supported_by | Evidence | Claim | Evidence supports the claim |
| contradicted_by | Evidence | Claim | Evidence contradicts the claim |
| derived_from | Claim | Study | Claim derived from study data |
| supersedes | Claim | Claim | New version supersedes old claim |
| references | Claim | Standard | Claim references a standard |
| generated_from | Report | Claim | Report section generated from claim |

## Requirements

### REQ-CLAIM-0001
The system shall store each claim as a structured object.

### REQ-CLAIM-0002
Each claim shall have a claim type, jurisdiction, language, lifecycle state and owner.

### REQ-CLAIM-0003
Each claim shall be linked to supporting evidence.

### REQ-CLAIM-0004
Each approved claim shall be reusable across reports and generated artifacts.

### REQ-CLAIM-0005
The system shall detect inconsistent approved claim wording across generated artifacts.

### REQ-CLAIM-0006
A claim shall not be approved without at least one evidence link or documented justification.

### REQ-CLAIM-0007
Each claim shall have a category (regulatory, clinical, analytical, scientific, marketing, safety, manufacturing, software).

### REQ-CLAIM-0008
Each claim shall have a severity classification (high, medium, low) indicating regulatory impact.

### REQ-CLAIM-0009
Each claim shall have a confidence level (high, medium, low) based on supporting evidence quality.

### REQ-CLAIM-0010
The system shall version claims and maintain full audit history of changes.

### REQ-CLAIM-0011
Each claim shall require at least one approved evidence relation before approval.

### REQ-CLAIM-0012
The system shall evaluate evidence coverage for each claim and report gaps.

### REQ-CLAIM-0013
Claim approval shall be blocked if evidence coverage is insufficient.

### REQ-CLAIM-0014
Claims shall be scoped to applicable regulatory frameworks (EU IVDR, EU MDR, FDA, UKCA, etc.).

### REQ-CLAIM-0015
Claims shall be referenceable from generated reports (PER, IFU, SSP, CER).

### REQ-CLAIM-0016
The system shall detect conflicting, duplicate or unsupported approved claims.

### REQ-CLAIM-0017
The system shall maintain a complete history of all claim versions, approvals and evidence links.

### REQ-CLAIM-0018
AI may propose claim wording, evidence candidates and consistency checks, but shall not approve claims.

## Interfaces

- Product Service — retrieves product context for claims
- Evidence Service — links evidence items to claims
- Risk Service — references claims in risk analyses
- Performance Service — links claims to performance results
- Report Service — inserts claims into generated reports
- AI Service — claim drafting and consistency checking

## Data Model

### ClaimPayload (Pydantic, extra='forbid')

| Field | Type | Required | Description |
|---|---|---|---|
| claim_type | str | Yes | clinical, analytical, performance, regulatory, safety, marketing, manufacturing, software |
| claim_category | str | Yes | regulatory, clinical, analytical, scientific, marketing, safety, manufacturing, software |
| confidence | str | Yes | high, medium, low |
| severity | str | Yes | high, medium, low |
| jurisdiction | str | Yes | EU/US/UK/CH/etc. |
| language | str | Yes | ISO language code |
| wording | str | Yes | Claim text content |
| regulatory_scope | List[str] | No | Applicable regulatory frameworks |
| notes | str | No | Internal notes |

## Acceptance Criteria

- A claim can be created with type, category, jurisdiction, language and wording.
- Evidence can be linked and unlinked to a claim.
- Claim approval is blocked when evidence coverage is insufficient.
- Claim consistency checker detects conflicts and duplicates.
- Claims are referenceable in generated reports.
- Unknown payload fields are rejected.

## Open Questions

- Should claim types be extensible via configuration?
- How to handle claims in multiple languages with version synchronization?
- Should the consistency checker run automatically on approval?
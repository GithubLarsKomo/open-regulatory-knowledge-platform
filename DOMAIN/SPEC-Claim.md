# SPEC-Claim.md

## Purpose

Define the claim domain.

## Scope

Claims include regulatory, clinical, analytical, performance, safety and marketing-relevant statements.

## Stakeholders

- Regulatory Affairs
- Clinical Evidence Reviewer
- Marketing
- Quality Management

## Domain Model

A Claim may be associated with:

- Product
- Intended purpose
- Performance study
- Scientific validity evidence
- Risk-benefit conclusion
- IFU section
- PER section
- SSP section
- Marketing text

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

## Acceptance Criteria

- A user can create a draft claim.
- A user can link evidence to a claim.
- A reviewer can approve or reject a claim.
- The claim can be inserted into a generated report.
- The system can list all reports using the claim.

## Interfaces

- Product Service — retrieves product context for claims
- Evidence Service — links evidence items to claims
- Risk Service — references claims in risk analyses
- Performance Service — links claims to performance results
- Report Service — inserts claims into generated reports

## Data Model

### claim

| Field | Type | Description |
|---|---|---|
| claim_uuid | UUID | Stable identifier |
| claim_type | VARCHAR | regulatory/clinical/analytical/performance/safety/marketing |
| jurisdiction | VARCHAR | EU/US/UK/CH/etc. |
| language | VARCHAR | ISO language code |
| wording | TEXT | Claim text content |
| lifecycle_state | VARCHAR | draft/in_review/approved/effective/obsolete |
| owner_user_id | VARCHAR | Responsible person |
| product_uuid | UUID | Linked product |
| created_at | DATETIME | Creation timestamp |
| updated_at | DATETIME | Last update timestamp |

### claim_evidence_link

| Field | Type | Description |
|---|---|---|
| link_uuid | UUID | Stable identifier |
| claim_uuid | UUID | Linked claim |
| evidence_uuid | UUID | Linked evidence item |
| link_type | VARCHAR | supports/contradicts |
| justification | TEXT | Optional justification if no evidence |

## Workflow

- Claim lifecycle: draft → in_review → approved → effective → obsolete
- Approval requires evidence link or documented justification per REQ-CLAIM-0006
- Rejected claims return to draft with reviewer comments

## Security

- Claim creation requires Regulatory Author role
- Claim approval requires Regulatory Approver role
- Claims visible per product-level permissions

## AI Support

- AI may propose claim wording (draft only)
- AI may detect inconsistent claim wording across artifacts (REQ-CLAIM-0005)
- AI may suggest evidence candidates for a claim
- AI shall not approve claims

## Open Questions

- Should claim types be extensible via configuration?
- How to handle claims in multiple languages with version synchronization?

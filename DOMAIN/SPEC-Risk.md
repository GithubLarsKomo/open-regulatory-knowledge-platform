# SPEC-Risk.md

## Purpose

Define the risk management domain according to ISO 14971 and IVDR expectations.

## Scope

The domain covers:

- Hazard identification and documentation
- Risk estimation and evaluation
- Risk control measures and verification
- Residual risk evaluation
- Benefit-risk analysis
- Risk Management Report generation
- Risk review and approval workflow

## Stakeholders

- QM Reviewer
- Regulatory Approver
- R&D
- Clinical Evidence Reviewer

## Domain Model

Core entities:

- Hazard
- Hazardous Situation
- Foreseeable Sequence of Events
- Harm
- Severity
- Probability
- Risk Estimate
- Risk Control
- Residual Risk
- Benefit-Risk Justification
- Verification of Control
- Risk Management Report

## Requirements

### REQ-RISK-0001
The system shall store hazards, hazardous situations, harms and risk estimates as structured objects.

### REQ-RISK-0002
Each risk shall be linked to one or more control measures where applicable.

### REQ-RISK-0003
Each control measure shall be linked to verification evidence.

### REQ-RISK-0004
Residual risk shall require documented evaluation before approval.

### REQ-RISK-0005
Risk objects shall be traceable to requirements, claims, verification and validation evidence.

### REQ-RISK-0006
The system shall support generation of a Risk Management Report from approved risk objects.

### REQ-RISK-0007
AI may propose risk justifications but shall not approve risk acceptability.

## Acceptance Criteria

- Risk objects can be created, versioned and approved.
- Traceability to controls and verification is visible.
- A change in risk control triggers impact analysis.
- A risk report section can be generated from approved objects.

## Interfaces

- Product Service — retrieves product context for risk files
- Claim Service — references claims in risk analysis
- Evidence Service — links verification evidence to risk controls
- Performance Service — links performance data to benefit-risk analysis
- Report Service — generates Risk Management Report sections

## Data Model

### hazard

| Field | Type | Description |
|---|---|---|
| hazard_uuid | UUID | Stable identifier |
| description | TEXT | Description of the hazard |
| lifecycle_state | VARCHAR | Lifecycle state |

### risk

| Field | Type | Description |
|---|---|---|
| risk_uuid | UUID | Stable identifier |
| hazard_uuid | UUID | Linked hazard |
| hazardous_situation | TEXT | Description of hazardous situation |
| foreseeable_sequence | TEXT | Sequence of events leading to harm |
| harm_description | TEXT | Description of potential harm |
| severity | VARCHAR | negligible/minor/moderate/critical/catastrophic |
| probability | VARCHAR | improbable/unlikely/possible/likely/probable |
| risk_estimate | VARCHAR | acceptable/unacceptable |
| residual_severity | VARCHAR | Severity after controls |
| residual_probability | VARCHAR | Probability after controls |
| residual_risk_estimate | VARCHAR | acceptable/unacceptable |
| lifecycle_state | VARCHAR | Lifecycle state |
| created_at | DATETIME | Creation timestamp |
| updated_at | DATETIME | Last update timestamp |

### risk_control

| Field | Type | Description |
|---|---|---|
| control_uuid | UUID | Stable identifier |
| risk_uuid | UUID | Linked risk |
| description | TEXT | Control measure description |
| verification_ref | UUID | Link to verification evidence |
| lifecycle_state | VARCHAR | Lifecycle state |

## Workflow

- Risk lifecycle: draft → in_review → approved → effective → obsolete
- Residual risk requires documented evaluation before approval (REQ-RISK-0004)
- Change in risk control triggers impact analysis

## Security

- Risk creation requires R&D Contributor or Regulatory Author role
- Risk approval requires QM Reviewer or Regulatory Approver role
- Risk acceptability decisions require documented approver identity

## AI Support

- AI may propose risk control suggestions (draft only)
- AI may identify missing controls based on similar device risks
- AI shall not approve risk acceptability (REQ-RISK-0007)
- AI confidence shall be visible for any risk-related suggestions

## Open Questions

- Should risk acceptance criteria be configurable per product?
- How to model benefit-risk analysis quantitatively vs. qualitatively?
- Should ISO 14973:2019 Annex C (risk management for in-house devices) be supported?

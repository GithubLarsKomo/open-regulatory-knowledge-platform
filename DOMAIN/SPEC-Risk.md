# SPEC-Risk.md

## Purpose

Define the risk management domain according to ISO 14971 principles and EU IVDR Annex I risk-related expectations.

## Scope

The domain covers:

- Hazard identification and documentation
- Foreseeable sequence of events, hazardous situations and harms
- Risk estimation with explicit severity and probability
- Initial and residual risk evaluation
- Risk control measures, hierarchy and verification
- Benefit-risk analysis
- Overall residual risk evaluation
- Production and post-production information feedback
- Risk Management Report generation
- Risk review and approval workflow

## Stakeholders

- QM Reviewer — evaluate risk acceptability
- Regulatory Approver — approve risk analyses
- R&D — contribute technical risk data
- Clinical Evidence Reviewer — assess clinical risk evidence
- Control Owner — implement risk controls
- Verification Reviewer — verify control effectiveness

## Architecture

Risks are stored as `RegulatoryObject` with `object_type='risk_analysis'` and related types for hazards, harms and controls. Risk chains link these objects via `ObjectRelation` with explicit version pinning.

```
Hazard --originates_from--> SequenceOfEvents
SequenceOfEvents --creates_situation--> HazardousSituation
HazardousSituation --may_cause--> Harm
RiskAnalysis --estimated_by--> HazardousSituation
RiskAnalysis --controlled_by--> RiskControl
Evidence --control_verified_by--> RiskControl
RiskAnalysis --applies_to_product--> Product
```

## Domain Boundaries

- Risk Analysis: the central aggregate that combines hazard → harm chains
- Risk Control: separate object, linked to one or more Risk Analyses
- Benefit-Risk Analysis: separate approved object for policy-gated progression
- Overall Residual Risk: product-level evaluation across all approved Risk Analyses

## Terminology

- Hazard: potential source of harm
- Foreseeable Sequence of Events: chain of events leading to hazardous situation
- Hazardous Situation: circumstance where persons are exposed to hazard
- Harm: injury or damage to health
- Severity: measure of harm potential
- Probability: likelihood of harm occurring
- Risk: combination of severity and probability
- Residual Risk: risk remaining after controls
- Benefit-Risk Analysis: comparison of residual risk against clinical benefit
- Overall Residual Risk: aggregate conclusion for a device

## Domain Model

### HazardPayload
- hazard_id, category, description, source, foreseeable_misuse

### SequenceOfEventsPayload
- sequence_id, description, initiating_event, intermediate_events, foreseeable_conditions

### HazardousSituationPayload
- situation_id, description, exposed_persons, exposure_context

### HarmPayload
- harm_id, description, harm_category, clinical_consequence

### RiskAnalysisPayload
- risk_id, title, rationale, severity, probability, risk_level, acceptability, estimation_method, uncertainty, assumptions

### RiskControlPayload
- control_id, title, description, control_option, implementation_status, owner, due_date, verification_required

### BenefitRiskPayload
- analysis_id, benefits, residual_risks, rationale, conclusion

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

### REQ-RISK-0008
The system shall distinguish Hazard, Foreseeable Sequence of Events, Hazardous Situation and Harm.

### REQ-RISK-0009
Risk estimates shall reference explicit Severity and Probability scales.

### REQ-RISK-0010
Initial and residual risk estimates shall be stored separately.

### REQ-RISK-0011
Risk controls shall follow a configurable control-option hierarchy.

### REQ-RISK-0012
Each implemented Risk Control shall require verification evidence.

### REQ-RISK-0013
The system shall evaluate risk acceptability using an approved Risk Policy.

### REQ-RISK-0014
Unacceptable residual risk shall require Benefit-Risk Analysis.

### REQ-RISK-0015
The system shall support Overall Residual Risk evaluation.

### REQ-RISK-0016
Risk objects shall be versioned and audit-trailed.

### REQ-RISK-0017
Risk relations shall reference explicit object versions.

### REQ-RISK-0018
Risk approval shall require complete traceability from Hazard to verification.

### REQ-RISK-0019
Production and post-production information shall be linkable to existing risks.

### REQ-RISK-0020
New safety information shall trigger Risk Impact Assessment.

### REQ-RISK-0021
Risk controls shall be linked to Requirements where applicable.

### REQ-RISK-0022
Risks shall be linked to Products or Devices.

### REQ-RISK-0023
Risk review findings shall use stable rule codes and severities.

### REQ-RISK-0024
Risk reports shall be reproducible from approved object baselines.

### REQ-RISK-0025
AI may draft risk rationales but shall never decide acceptability.

## Interfaces

- Product Service — retrieves product context for risk files
- Claim Service — references claims in risk analysis
- Evidence Service — links verification evidence to risk controls
- Performance Service — links performance data to benefit-risk analysis
- Report Service — generates Risk Management Report sections

## Data Model

See `src/orkp/domain/risk_models.py` for strict Pydantic payload models.

## Workflow

Risk lifecycle: draft → in_review → approved → effective → obsolete
Initial risk → controls → residual risk → evaluation → benefit-risk if needed → approval

## Security

- Risk Author must not approve own analyses
- Risk Approver role required for final approval
- Control Owner must not be sole verification approver

## AI Support

- AI may draft risk justifications (draft only)
- AI shall never decide risk acceptability

## Acceptance Criteria

- Full hazard → harm chain can be created and linked.
- Initial risk can be evaluated using configurable policy.
- Controls can be linked to risks and verification evidence.
- Residual risk is evaluated separately.
- Benefit-Risk Analysis is required for unacceptable residual risk.
- Overall Residual Risk aggregates all approved analyses.
- Risk approval requires complete traceability.

## Open Questions

- Should probability follow a numeric or ordinal scale?
- How to model multi-device risk files?
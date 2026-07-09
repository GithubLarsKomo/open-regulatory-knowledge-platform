# SPEC-KnowledgeGraph.md

## Purpose

Define the graph representation for regulatory traceability and impact analysis.

## Node Types

- Product
- Device
- Requirement
- Claim
- Hazard
- Risk
- RiskControl
- Verification
- Validation
- Study
- Evidence
- Report
- ReportSection
- Standard
- Regulation
- Submission

## Edge Types

- HAS_REQUIREMENT
- SUPPORTS_CLAIM
- MITIGATES
- VERIFIED_BY
- VALIDATED_BY
- REFERENCES
- INCLUDED_IN
- GENERATED_FROM
- IMPACTS
- SUPERSEDES

## Requirements

### GRAPH-CORE-0001
The graph shall represent traceability relationships between regulatory objects.

### GRAPH-CORE-0002
The graph shall support impact analysis after changes to claims, risks, evidence or requirements.

### GRAPH-CORE-0003
The graph shall distinguish object identity from object version where required.

### GRAPH-CORE-0004
The graph shall not be the primary approval record; approval authority remains in the object store and event store.

## Example Query

```cypher
MATCH (c:Claim)-[:SUPPORTED_BY]->(e:Evidence)-[:DERIVED_FROM]->(s:Study)
WHERE c.claim_id = $claimId
RETURN c, e, s
```

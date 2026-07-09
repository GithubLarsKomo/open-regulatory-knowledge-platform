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

## Scope

The knowledge graph covers:

- Traceability relationships between all regulatory object types
- Impact analysis for change management
- Object version-aware graph queries
- Cross-domain relationship visualization
- Compliance and gap analysis queries

## Stakeholders

- Regulatory Authors — traceability analysis
- QM Reviewers — impact assessment
- Auditors — traceability verification
- System Developers — graph queries

## Domain Model

### Node Types

- Product, Device — product hierarchy
- Requirement — regulatory and system requirements
- Claim — regulatory claims
- Hazard, Risk, RiskControl — risk management
- Verification, Validation — evidence of conformity
- Study, Evidence — performance and literature
- Report, ReportSection — generated outputs
- Standard, Regulation — applicable norms
- Submission — regulatory submission packages

### Edge Types

- HAS_REQUIREMENT — product-to-requirement
- SUPPORTS_CLAIM — evidence-to-claim
- MITIGATES — control-to-risk
- VERIFIED_BY — requirement-to-verification
- VALIDATED_BY — requirement-to-validation
- REFERENCES — object-to-literature
- INCLUDED_IN — section-to-report
- GENERATED_FROM — report-to-baseline
- IMPACTS — change propagation
- SUPERSEDES — version supersession

## Interfaces

- Object Store — synchronization source
- REST API — graph query endpoints
- UI — graph visualization
- Report Engine — traceability appendix

## Data Model

### Node Properties

| Property | Type | Description |
|---|---|---|
| node_uuid | UUID | Stable identifier |
| node_type | VARCHAR | Node type label |
| object_version | INT | Object version (if applicable) |
| label | VARCHAR | Display label |
| lifecycle_state | VARCHAR | Current state |

### Edge Properties

| Property | Type | Description |
|---|---|---|
| edge_type | VARCHAR | Relationship type |
| source_version | INT | Source object version |
| target_version | INT | Target object version |
| created_at | DATETIME | Relationship timestamp |

## Workflow

- Graph is synchronized from object store events
- Version changes trigger edge updates
- Impact analysis queries are initiated by users
- Graph does not replace object store for approval

## Security

- Graph access respects RBAC permissions
- Product-scoped users see only relevant subgraph
- Graph is read-only for non-administrators

## AI Support

- AI may propose graph queries in natural language
- AI may highlight impacted paths on change
- AI cannot modify graph structure

## Acceptance Criteria

- A traceability query returns all linked objects for a claim.
- Impact analysis identifies all objects affected by a risk change.
- Graph distinguishes object versions.
- Approval remains in object store, not graph.

## Open Questions

- Should the graph be updated synchronously or asynchronously?
- What is the maximum practical graph size?
- Should the graph support full-text search on node properties?

## Example Query

```cypher
MATCH (c:Claim)-[:SUPPORTED_BY]->(e:Evidence)-[:DERIVED_FROM]->(s:Study)
WHERE c.claim_id = $claimId
RETURN c, e, s
```

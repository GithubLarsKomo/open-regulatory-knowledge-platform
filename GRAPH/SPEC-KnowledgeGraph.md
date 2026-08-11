# SPEC-KnowledgeGraph.md

## Purpose

Define the graph representation for regulatory traceability and impact analysis.

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

## Requirements

### GRAPH-CORE-0001
The graph shall represent traceability relationships between regulatory objects.

### GRAPH-CORE-0002
The graph shall support impact analysis after changes to claims, risks, evidence or requirements.

### GRAPH-CORE-0003
The graph shall distinguish object identity from object version where required.

### GRAPH-CORE-0004
The graph shall not be the primary approval record; approval authority remains in the object store and event store.

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

- Object Store — synchronization source and approval authority
- REST API — graph query endpoints
- UI — graph visualization
- Report Engine — traceability appendix

## Data Model

### Node Properties

| Property | Type | Description |
|---|---|---|
| node_uuid | UUID | Stable object identifier |
| node_type | VARCHAR | Node type label |
| object_version | INT | Exact Object Store version |
| label | VARCHAR | Display label derived from the exact version payload |
| lifecycle_state | VARCHAR | Current Object Store state |
| version_status | VARCHAR | Exact Object Version status |
| is_current_version | BOOLEAN | Whether this node represents the current object version |

Canonical graph-node identity is the pair `(node_uuid, object_version)`. Two versions of the same regulatory object are distinct graph nodes where version-aware traceability is required.

### Edge Properties

| Property | Type | Description |
|---|---|---|
| relation_uuid | UUID | Stable Object Store relationship identifier |
| edge_type | VARCHAR | Relationship type |
| source_version | INT | Exact source object version |
| target_version | INT | Exact target object version |
| created_at | DATETIME | Relationship timestamp |

Only active Object Store relations are part of the current traceability projection. Graph edges do not create independent regulatory relationships.

## Canonical Traceability Projection

Before a Neo4j synchronization adapter is introduced, the platform exposes a canonical read-only projection directly from Object Store versions and active relations.

The projection contract is:

- exact root object UUID and version are mandatory;
- incoming and outgoing active relations are traversed;
- every node keeps object identity and object version separate;
- historical versions remain queryable after newer versions exist;
- inactive relations are excluded;
- output is deterministic and duplicate-free;
- traversal depth is explicitly bounded;
- graph queries do not mutate objects, versions, relations, lifecycle state or approval records;
- every graph response declares the Object Store as approval authority.

REST reference interface:

`GET /api/v1/graph/objects/{object_uuid}/versions/{object_version}/traceability?depth=1`

The Neo4j synchronization layer shall materialize the same canonical identity/version/relation semantics rather than define a separate regulatory truth.

## Workflow

- Graph is synchronized from object store events
- Version changes trigger edge updates
- Impact analysis queries are initiated by users
- Graph does not replace object store for approval

Until the Neo4j synchronization adapter is enabled, the canonical traceability projection is evaluated read-only against the Object Store. This preserves one source of regulatory truth while establishing the exact graph contract for synchronization.

## Security

- Graph access respects RBAC permissions
- Product-scoped users see only relevant subgraph
- Graph is read-only for non-administrators

RBAC filtering is implemented with the Workflow & Security epic and is not inferred by the graph layer itself.

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
MATCH (e:Evidence)-[:SUPPORTED_BY]->(c:Claim),
      (e)-[:DERIVED_FROM]->(s:Study)
WHERE c.claim_id = $claimId
RETURN c, e, s
```

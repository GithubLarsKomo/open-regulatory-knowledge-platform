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

The platform exposes a canonical read-only projection directly from Object Store versions and active relations.

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

Any materialized graph layer shall reproduce the same canonical identity/version/relation semantics rather than define a separate regulatory truth.

## Change Impact Analysis

Impact analysis uses the same canonical exact-version projection. A changed root is always identified by the pair `(object_uuid, object_version)`; the graph shall not silently substitute the object's current version.

The initial deterministic propagation policy is `bidirectional_active_relations`:

- only active relations pinned to the exact changed version are traversed;
- incoming and outgoing relations are both considered because regulatory review obligations can propagate in either structural direction;
- every reachable exact-version node within the bounded depth is reported as potentially impacted;
- the changed root itself is not repeated as an impacted node;
- every impacted node includes its graph distance and one deterministic shortest path from the changed root;
- the path includes exact object UUID/version references and exact relation UUIDs;
- inactive relations are excluded;
- no relation-type-specific causal weight, severity, or automatic regulatory conclusion is inferred by this baseline policy.

REST reference interface:

`GET /api/v1/graph/objects/{object_uuid}/versions/{object_version}/impact?depth=2`

Impact results are read-only analysis aids. Approval decisions and change-control authority remain in the Object Store and Event Store.

## Deterministic Synchronization Contract

Graph synchronization consumes the same canonical `TraceabilityGraph` projection and does not define a second graph semantics.

Each synchronization request is represented as `graph-sync-batch-1.0` and contains:

- exact root object UUID/version and bounded depth through the canonical graph payload;
- `source_authority = object_store`;
- `approval_authority = object_store`;
- `read_only = true` from the regulatory-authority perspective;
- `sync_mode = replace_exact_scope`;
- canonical JSON for the exact scope and a SHA-256 checksum over that canonical payload.

The synchronization adapter is infrastructure-neutral. A concrete adapter receives the immutable batch and must acknowledge the exact checksum, root, depth, node count and edge count that it applied. Any mismatch is a synchronization failure.

`replace_exact_scope` means that a concrete graph adapter must make the materialized scope correspond to the submitted canonical scope rather than silently merging unbounded stale data. The synchronization layer must not change Object Store objects, versions, relations, lifecycle state or approvals.

## Neo4j Materialization

Neo4j is an optional derived read-model implementation of the synchronization contract.

The materialization uses static infrastructure identifiers:

- `:ORKPObjectVersion` nodes represent exact object UUID/version pairs;
- `:ORKPSyncScope` nodes represent stable root UUID/root version/depth synchronization scopes;
- `:ORKP_RELATION` relationships represent exact Object Store relation UUIDs;
- original `object_type` and `relation_type` values are stored as properties rather than interpolated into Cypher labels or relationship types.

The Neo4j schema uses idempotent property-uniqueness constraints for:

- `(object_uuid, object_version)` on `ORKPObjectVersion`;
- `scope_key` on `ORKPSyncScope`;
- `relation_uuid` on `ORKP_RELATION`.

Exact-scope replacement occurs atomically in one explicit write transaction. Nodes and relationships keep a list of synchronized `scope_keys`. Replacing one scope removes only that scope membership, then upserts the submitted canonical scope. Relationships and nodes are deleted only when they have no remaining scope membership. Node cleanup is non-detaching so an unexpected shared relationship causes the transaction to fail instead of being silently removed.

Canonical relation metadata that may contain nested structures is serialized as deterministic JSON rather than expanded as arbitrary Neo4j properties.

The concrete adapter is optional infrastructure. Core ORKP remains importable and usable without the Neo4j Python package installed.

Neo4j never becomes approval authority.

## Workflow

- Canonical graph queries are evaluated from the Object Store.
- Exact scopes may be materialized into Neo4j through the deterministic synchronization contract.
- Version changes may later trigger synchronization through an event/outbox mechanism.
- Impact analysis queries are initiated by users.
- Graph infrastructure does not replace the Object Store for approval.

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
- Impact analysis identifies all exact-version objects connected to a changed risk within the configured depth and returns deterministic supporting paths.
- Graph distinguishes object versions.
- Approval remains in object store, not graph.

## Open Questions

- Should synchronization be triggered synchronously or through an outbox worker?
- What is the maximum practical graph size?
- Should the graph support full-text search on node properties?

## Example Query

```cypher
MATCH (e:Evidence)-[:SUPPORTED_BY]->(c:Claim),
      (e)-[:DERIVED_FROM]->(s:Study)
WHERE c.claim_id = $claimId
RETURN c, e, s
```

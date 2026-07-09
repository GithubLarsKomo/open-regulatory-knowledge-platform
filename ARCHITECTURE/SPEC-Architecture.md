# SPEC-Architecture.md

## Purpose

Define the target architecture for the Open Regulatory Knowledge Platform.

## Architecture Overview

The system shall use a modular service architecture.

```text
Web UI
  |
API Gateway
  |
Domain Services
  |
Object Store ---- Event Store
  |                 |
Knowledge Graph    Audit Trail
  |
Vector Index
  |
Report Engine / AI Engine / Workflow Engine
```

## Scope

The architecture covers:

- Service layering and separation of concerns
- Multi-representation support (relational, graph, vector)
- Event sourcing for audit and reproducibility
- API-first design principles
- Baseline-based report reproducibility
- Deployment architecture and scaling

## Stakeholders

- System Architects — define and maintain architecture
- Developers — implement within architectural guidelines
- DevOps — deployment and infrastructure
- Regulatory Affairs — validation and audit requirements

## Requirements

### REQ-ARCH-0001
The platform shall separate domain logic from persistence technology.

### REQ-ARCH-0002
The platform shall expose all core regulatory objects through APIs.

### REQ-ARCH-0003
The platform shall support relational, graph and vector-based representations of regulatory knowledge.

### REQ-ARCH-0004
The platform shall support event sourcing for regulatory object lifecycle changes.

### REQ-ARCH-0005
The platform shall allow generated reports to be reproduced from historical baselines.

## Domain Model

### Service Layers

```text
+------------------+
|    Web UI        |  Presentation Layer
+------------------+
|   API Gateway    |  API Layer (REST)
+------------------+
| Domain Services  |  Business Logic Layer
+------------------+
| Object Store     |  Persistence Layer (MariaDB)
| Event Store      |  Event Sourcing Layer
+------------------+
| Knowledge Graph  |  Graph Layer (Neo4j)
| Vector Index     |  Semantic Layer
+------------------+
| Report Engine    |  Generation Layer
| AI Engine        |  AI/RAG Layer
| Workflow Engine  |  Orchestration Layer
+------------------+
```

## Interfaces

- REST API — external and UI communication
- Inter-service event bus — domain event propagation
- Graph synchronization — object store to Neo4j
- Vector indexing — object store to vector index
- Report Engine — template rendering
- AI Engine — retrieval-augmented generation

## Data Model

### Core Domain Object

| Property | Description |
|---|---|
| UUID | Stable, immutable identifier |
| Object Type | Domain classification |
| Version | Monotonic version counter |
| Lifecycle State | Current workflow state |
| JSON Payload | Type-specific data |
| Audit Metadata | Creator, timestamps, history |

## Workflow

1. API receives request → authenticates → authorizes
2. Domain Service validates → applies business logic
3. Object Store persists → Event Store records event
4. Graph syncs (asynchronous) → Vector indexes (asynchronous)
5. Report Engine reads from stores → generates output

## Security

- All inter-service communication over TLS
- Authentication required at API gateway
- Role-based authorization per service
- Audit trail for all state changes
- Separation of duties enforced at service level

## AI Support

- AI Engine is a separate service, not embedded
- AI accesses data through read-only API
- AI output is stored as draft, never directly approved
- AI audit trail separate from regulatory audit trail

## Acceptance Criteria

- A new domain can be added by creating Service + Schema + API.
- A report can be regenerated from a baseline.
- Event log covers all state changes.
- Graph and vector index stay synchronized.

## Open Questions

- Should the API gateway include rate limiting and caching?
- What event bus technology (RabbitMQ, Kafka, NATS)?
- Should services be deployed as monolith first, then split?

## Service Candidates

- Product Service
- Claim Service
- Risk Service
- Evidence Service
- Performance Service
- Report Service
- Workflow Service
- AI Service
- Audit Service
- Identity and Access Service

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

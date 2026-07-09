# ADR-0002 — MariaDB as Relational Reference Implementation

## Status

Proposed

## Context

A relational database is required for transactions, versioned object storage, reporting and operational consistency.

## Decision

MariaDB shall be supported as a reference relational implementation.

## Consequences

Positive:

- Strong SQL support
- Operational familiarity
- Good fit for structured regulatory data

Negative:

- Graph traversal is limited compared to Neo4j
- JSON governance requires discipline

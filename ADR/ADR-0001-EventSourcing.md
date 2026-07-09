# ADR-0001 — Event Sourcing

## Status

Proposed

## Context

Regulatory systems require complete reconstruction of historical states, auditability and reproducible submissions.

## Decision

The platform shall use event sourcing for regulatory object lifecycle events.

## Consequences

Positive:

- Full auditability
- Historical reconstruction
- Impact analysis
- Reproducible baselines

Negative:

- Higher implementation complexity
- Need for careful event schema versioning
- Requires strong developer discipline

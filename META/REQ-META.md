# REQ-META.md

## Purpose

Define formal requirements for the specification meta-layer: ID scheme compliance and task generation rules.

## Requirements

### META-ID-0001
The system shall enforce a unique, immutable identifier scheme for all requirements, tasks and tests according to the format `PREFIX-DOMAIN-NNNN`.

### META-TASK-0001
The system shall generate SWE tasks from SPEC files, where each task references at least one requirement ID and follows the defined task structure.

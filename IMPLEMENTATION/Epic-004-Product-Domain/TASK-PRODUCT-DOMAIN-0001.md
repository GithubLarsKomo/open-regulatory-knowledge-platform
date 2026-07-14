# TASK-PRODUCT-DOMAIN-0001 — Implement Product Domain MVP

## Task ID

TASK-PRODUCT-DOMAIN-0001

## Title

Implement Product Domain MVP

## Source Requirements

- REQ-PROD-0001 through REQ-PROD-0020

## Goal

Implement the Product domain as the reference architecture for all future regulatory domains within ORKP.

## Background

The Product domain is the central regulatory anchor. All other domains (Claims, Risks, Evidence, Performance Studies, Submissions) will reference products. This implementation establishes the architectural pattern for all future domains.

## Architecture

- Product is `RegulatoryObject` with `object_type='product'`
- Device is `RegulatoryObject` with `object_type='device'` (separate, not embedded)
- Relationships use `ObjectRelation` with explicit version references
- Payload validation via `ProductPayload` and `DevicePayload` (Pydantic, `extra='forbid'`)
- `ProductService` wraps `RegulatoryObjectRepository`
- Completeness evaluation via `product_completeness.py`
- Approval gate enforces completeness before transition

## Scope

- ProductPayload with strict validation (enums, min_length, no duplicates, no unknown fields)
- DevicePayload as separate model
- ProductService with complete API (create, get, list, update, submit, approve, reject, delete)
- DeviceService for device operations
- Product completeness evaluator with scoring
- Versioned relationships: has_claim, has_risk, has_evidence, variant_of
- Product-specific API endpoints
- ProductCompletenessError typed exception
- Unit and integration tests

## Non-Scope

- Economic operators (future batch)
- Multi-site manufacturers (future batch)
- Regulatory submissions referencing products
- PMS/PMPF data linked to products
- Performance studies linked to products
- UI for product management
- AI-assisted product data entry

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | /api/v1/products | Create product |
| GET | /api/v1/products | List products |
| GET | /api/v1/products/{uuid} | Get product detail |
| POST | /api/v1/products/{uuid}/submit | Submit for review |
| POST | /api/v1/products/{uuid}/approve | Approve (with completeness check) |
| DELETE | /api/v1/products/{uuid} | Soft-delete |
| POST | /api/v1/products/{uuid}/devices | Add device variant |
| GET | /api/v1/products/{uuid}/devices | List device variants |
| POST | /api/v1/products/{uuid}/claims/{claim} | Link claim |
| POST | /api/v1/products/{uuid}/risks/{risk} | Link risk |
| POST | /api/v1/products/{uuid}/evidence/{evidence} | Link evidence |
| GET | /api/v1/products/{uuid}/completeness | Get completeness evaluation |

## Acceptance Criteria

1. Product can be created with mandatory fields and validated product_kind.
2. Unknown payload fields are rejected (422).
3. Invalid product_kind values are rejected (422).
4. Duplicate applicable_regulations are rejected (422).
5. Device variant can be created as separate RegulatoryObject.
6. Device creation is atomic with variant_of relation.
7. Product completeness evaluation returns structured result.
8. Product approval is blocked when completeness fails.
9. Product approval succeeds when completeness passes.
10. Typed exceptions are raised for state-changing operations.
11. All relationships are versioned.

## Unit Tests

- test_create_product
- test_reject_unknown_fields
- test_reject_invalid_product_kind
- test_reject_duplicate_regulations
- test_add_device_variant
- test_list_device_variants
- test_product_completeness
- test_approve_fails_without_completeness
- test_approve_succeeds_with_completeness
- test_link_claim_and_risk
- test_typed_exceptions_preserved

## Definition of Done

- ProductPayload and DevicePayload with `extra='forbid'` and validators
- ProductService with complete lifecycle
- DeviceService with create and list
- Product completeness evaluator
- Product API endpoints
- Architecture document (ARCHITECTURE/Product-Domain.md)
- All unit tests pass
- `python -m pytest -q` passes
- `python tools/spec_linter.py --strict` passes
- Generated artifacts are up to date

## Future Extensions

- Economic operators as separate domain
- Product-to-submission relations
- Product-to-PMS relations
- Multi-site manufacturer support
- AI-assisted intended purpose drafting
- Product comparison and version diff
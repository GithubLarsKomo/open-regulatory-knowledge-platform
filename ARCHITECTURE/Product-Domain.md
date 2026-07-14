# Product Domain Architecture

## Domain Boundaries

The Product domain is the central regulatory anchor for all product-related information within ORKP. It manages:

- Product master data (regulatory identifiers, classification, status)
- Device variants (configurations, UDI-DI, market status)
- Product relationships to claims, risks, evidence, and submissions
- Product completeness evaluation for approval gates

## Aggregate Roots

### Product

The Product is the primary aggregate root. It is stored as a `RegulatoryObject` with `object_type='product'`. The payload is validated by `ProductPayload` (Pydantic, `extra='forbid'`).

### Device

A Device is a separate aggregate root stored as a `RegulatoryObject` with `object_type='device'`. It is never embedded in the Product payload. Relationships are modelled via `ObjectRelation`.

## Repository Usage

The `RegulatoryObjectRepository` is the single data access layer for all domain objects. Domain services wrap the repository and provide type-safe methods.

```
ProductService(repo) --> RegulatoryObjectRepository --> SQLAlchemy Session
DeviceService(repo)  --> RegulatoryObjectRepository --> SQLAlchemy Session
```

## Versioning

Every Product and Device is versioned. The `object_version` table stores immutable snapshots. Relationships reference explicit source and target versions:

```
ObjectRelation(
    source_uuid=device.uuid,
    source_version=1,
    target_uuid=product.uuid,
    target_version=3,
    relation_type='variant_of'
)
```

## Lifecycle

The standard lifecycle applies to all Product and Device objects:

```
draft → in_review → approved → effective → obsolete
    ↑         ↓
    └── rejected
```

## ObjectRelation Usage

| Relation Type | Source | Target | Description |
|---|---|---|---|
| variant_of | Device | Product | Device belongs to product family |
| has_claim | Product | Claim | Product makes a regulatory claim |
| has_risk | Product | Risk | Product has a documented risk |
| has_evidence | Product | Evidence | Product has supporting evidence |
| governed_by | Product | Regulation | Product is governed by a regulation |
| manufactured_by | Product | Organization | Product is manufactured by an organization |

## Approval Workflow

1. Product is created in `draft` state.
2. Author links claims, risks, evidence via versioned relations.
3. Author submits for review → `in_review`.
4. Completeness evaluation runs:
   - Mandatory fields: product_id, name, legal_manufacturer, intended_purpose, regulatory_status
   - Mandatory relations: at least one has_claim, at least one has_risk
5. If incomplete → `ProductCompletenessError` raised, approval blocked.
6. If complete → `approved` state.
7. Optional: `effective` → `obsolete` transitions.

## Completeness Evaluation

The completeness engine (`product_completeness.py`) returns:

```json
{
    "complete": false,
    "score": 57,
    "missing_required_fields": [],
    "missing_relationships": ["at least one claim relation"],
    "warnings": ["No applicable regulations defined for assay/kit product"]
}
```

## Interaction with Future Domains

The Product domain is the template for all future domains:

- **Claim Domain** — same pattern: separate RegulatoryObject, versioned relations, completeness checking
- **Risk Domain** — same pattern, linked to Product via has_risk
- **Evidence Domain** — same pattern, linked to Product via has_evidence
- **Performance Studies** — linked to Product via has_study
- **Regulatory Submissions** — reference Product baselines

The pattern is:

1. Define Pydantic payload with `extra='forbid'`
2. Use `RegulatoryObject` for persistence
3. Use `ObjectRelation` for cross-domain links
4. Implement service with typed exceptions
5. Implement completeness evaluation
6. Expose via typed API endpoints
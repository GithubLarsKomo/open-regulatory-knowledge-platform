# SPEC-Product.md

## Purpose

Define the product and device master data domain as the central regulatory anchor for all product-related information.

## Scope

The domain covers:

- Product master data and regulatory identifiers
- Device hierarchy and variants
- Component and accessory documentation
- Product lifecycle states and governance
- Regulatory identifiers (UDI-DI, Basic UDI-DI, IVDR codes, EMDN, GMDN)
- Intended purpose and target population
- Legal manufacturer and economic operators
- Applicable regulations and notified body
- Product completeness evaluation
- Versioned relationships to claims, risks, evidence, submissions

## Stakeholders

- Regulatory Affairs — define and maintain product data
- R&D — contribute technical product specifications
- Product Management — own product portfolio
- Quality Management — review and approve product data
- Notified Body — review submissions referencing product data

## Architecture

Products are stored as `RegulatoryObject` with `object_type='product'`.
Device variants are stored as separate `RegulatoryObject` with `object_type='device'`.

Relationships between products and other domain objects are modelled as
versioned `ObjectRelation` rows:

```
Product --has_claim--> Claim
Product --has_risk--> Risk
Product --has_evidence--> Evidence
Device --variant_of--> Product
```

The payload schema is defined in `ProductPayload` (Pydantic) with `extra='forbid'`.

## Domain Model

### Core Entities

- **Product** — a commercially distinct device family (RegulatoryObject)
- **Device** — a specific variant or configuration (RegulatoryObject)
- **ProductLifecycle** — lifecycle state tracking per product

### Product Associations

A Product may be associated with:

- One or more Devices (via variant_of relation)
- Intended purpose
- Target population
- Claims (via has_claim relation)
- Risks (via has_risk relation)
- Evidence (via has_evidence relation)
- Performance studies
- Regulatory submissions
- PMS/PMPF data
- Legal manufacturer and economic operators
- Applicable regulations

## Requirements

### REQ-PROD-0001
The system shall store products with a unique product identifier, name, description and product owner.

### REQ-PROD-0002
The system shall support device hierarchy where a product has one or more device variants.

### REQ-PROD-0003
The system shall store regulatory identifiers including UDI-DI, Basic UDI-DI, GMDN code, IVR code and manufacturer references.

### REQ-PROD-0004
The system shall store intended purpose, target population and clinical indications.

### REQ-PROD-0005
The system shall link products to their applicable regulations and notified body.

### REQ-PROD-0006
The system shall link products to related claims, risks, performance studies and requirements.

### REQ-PROD-0007
The system shall support product lifecycle states with corresponding workflow transitions.

### REQ-PROD-0008
A product shall have a product type classification chosen from a controlled vocabulary (assay, kit, reagent, software, instrument, accessory, control, calibrator, specimen_receptacle).

### REQ-PROD-0009
Device variants shall be stored as separate `RegulatoryObject` instances with `object_type='device'`, not embedded in product payload.

### REQ-PROD-0010
The system shall distinguish Basic UDI-DI (product family level) from UDI-DI (device variant level) and maintain both where applicable.

### REQ-PROD-0011
Each product shall reference a legal manufacturer with name and SRN number.

### REQ-PROD-0012
The system shall support associating economic operators (manufacturer, authorised representative, importer, distributor) with products via versioned relations.

### REQ-PROD-0013
The intended purpose shall be a mandatory field with controlled vocabulary or free-text validation.

### REQ-PROD-0014
Products shall reference applicable regulations (e.g. EU 2017/746, EU 2017/745) without duplicates.

### REQ-PROD-0015
Each product shall have a regulatory status (development, verification, validation, submitted, registered, marketed, discontinued).

### REQ-PROD-0016
The system shall evaluate product completeness using a structured scoring engine that checks mandatory fields, mandatory relationships and warnings.

### REQ-PROD-0017
Product approval shall be blocked if the completeness evaluation does not pass minimum requirements.

### REQ-PROD-0018
All relationships between products and other domain objects shall reference explicit object versions and be stored in the object_relation table.

### REQ-PROD-0019
Product payloads shall be validated with strict Pydantic schemas that reject unknown fields, validate enum values and enforce uniqueness constraints.

### REQ-PROD-0020
Device variant creation shall be atomic: device object creation, versioned relation creation and audit events must succeed or fail together.

## Interfaces

- Claim Service — retrieves claims linked to product
- Risk Service — retrieves risk files linked to product
- Evidence Service — retrieves evidence linked to product
- Performance Service — retrieves studies linked to product
- Report Service — uses product data in generated reports
- IAM Service — enforces product-specific permissions

## Data Model

### Product Payload (Pydantic)

| Field | Type | Required | Description |
|---|---|---|---|
| product_id | str | Yes | Business key |
| name | str | Yes | Product name |
| product_kind | enum | Yes | ASSAY, KIT, REAGENT, SOFTWARE, INSTRUMENT, ACCESSORY, CONTROL, CALIBRATOR, SPECIMEN_RECEPTACLE |
| legal_manufacturer | str | Yes | Legal manufacturer name |
| intended_purpose | str | Yes | Intended purpose statement |
| regulatory_status | enum | Yes | DEVELOPMENT, VERIFICATION, VALIDATION, SUBMITTED, REGISTERED, MARKETED, DISCONTINUED |
| description | str | No | Product description |
| basic_udi_di | str | No | Basic UDI-DI per EU IVDR/MDR |
| emdn_code | str | No | EMDN code |
| gmdn_code | str | No | GMDN code |
| ivr_code | str | No | IVR code (IVDR) |
| manufacturer_srn | str | No | Manufacturer SRN number |
| notified_body_number | str | No | Notified body number |
| risk_class | str | No | Risk classification class |
| target_population | str | No | Target patient population |
| specimen_types | List[str] | No | Specimen types (no duplicates) |
| clinical_indications | str | No | Clinical indications |
| contraindications | str | No | Contraindications |
| applicable_regulations | List[str] | No | Applicable regulations (no duplicates) |

### Device Payload (Pydantic)

| Field | Type | Required | Description |
|---|---|---|---|
| device_id | str | Yes | Business key |
| name | str | Yes | Device variant name |
| device_kind | str | Yes | Device kind description |
| udi_di | str | No | UDI-DI |
| catalogue_number | str | No | Catalogue number |
| configuration | str | No | Configuration variant description |
| software_version | str | No | Software version where applicable |
| market_status | str | No | Market status |

## Workflow

- Product lifecycle: draft → in_review → approved → effective → obsolete
- Product approval requires completeness check (REQ-PROD-0017)
- Device creation is atomic with variant_of relation (REQ-PROD-0020)
- All relationships are versioned (REQ-PROD-0018)

## Security

- Product-level permissions per SEC-RBAC-0002
- Access scoped to assigned products
- Approval requires role distinct from authoring role

## AI Support

- AI may propose intended purpose wording (draft only)
- AI may suggest GMDN/EMDN code candidates
- AI may assist completeness gap analysis
- AI shall not assign regulatory identifiers without human verification
- AI shall not approve products

## Acceptance Criteria

- A product can be created with mandatory identifiers and validated product_kind.
- A device variant can be added as a separate object with variant_of relation.
- Claims, risks and evidence can be linked to a product.
- Product completeness is evaluated and blocks approval when incomplete.
- Unknown payload fields are rejected.
- Duplicate applicable_regulations are rejected.
- Product data appears in generated report sections.

## Open Questions

- Should reprocessing information be part of Product or a separate domain?
- How to model kit products containing multiple IVD components?
- Should economic operators be a separate domain or part of Product?
- How to handle multi-site manufacturers?
# SPEC-Product.md

## Purpose

Define the product and device master data domain.

## Scope

The domain covers:

- Product master data
- Device hierarchy and variants
- Component and accessory documentation
- Product lifecycle states
- Regulatory identifiers (UDI-DI, Basic UDI-DI, IVDR codes, GMDN)
- Intended purpose and target population

## Stakeholders

- Regulatory Affairs
- R&D
- Product Management
- Quality Management

## Domain Model

A Product may be associated with:

- One or more Devices (variants)
- Intended purpose
- Target population
- Claims
- Risks
- Performance studies
- Requirements
- Regulatory submissions
- PMS/PMPF data

### Core Entities

- Product — a commercially distinct device family
- Device — a specific variant or configuration
- Component — a sub-assembly or part
- Accessory — an accessory device per IVDR definition
- ProductLifecycle — lifecycle state tracking per product

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

## Interfaces

- Claim Service — retrieves claims linked to product
- Risk Service — retrieves risk files linked to product
- Performance Service — retrieves studies linked to product
- Report Service — uses product data in generated reports
- IAM Service — enforces product-specific permissions

## Data Model

### Product

| Field | Type | Description |
|---|---|---|
| product_uuid | UUID | Stable identifier |
| product_id | VARCHAR | Business key |
| name | VARCHAR | Product name |
| description | TEXT | Product description |
| intended_purpose_id | UUID | Link to intended purpose |
| basic_udi_di | VARCHAR | Basic UDI-DI per EU MDR/IVDR |
| gmdn_code | VARCHAR | GMDN code |
| ivr_code | VARCHAR | IVR code (IVDR) |
| manufacturer_name | VARCHAR | Legal manufacturer |
| notified_body | VARCHAR | Notified body reference |
| lifecycle_state | VARCHAR | draft/active/obsolete |
| owner_user_id | VARCHAR | Responsible person |
| created_at | DATETIME | Creation timestamp |
| updated_at | DATETIME | Last update timestamp |

### Device

| Field | Type | Description |
|---|---|---|
| device_uuid | UUID | Stable identifier |
| product_uuid | UUID | Parent product |
| device_id | VARCHAR | Business key |
| name | VARCHAR | Device variant name |
| udi_di | VARCHAR | UDI-DI |
| lifecycle_state | VARCHAR | Lifecycle state |

## Workflow

- Product lifecycle: draft → active → obsolete
- Product approval requires completeness check on linked claims and risks

## Security

- Product-level permissions per SEC-RBAC-0002
- Access scoped to assigned products

## AI Support

- AI may propose intended purpose wording (draft only)
- AI may suggest GMDN code candidates
- AI shall not assign regulatory identifiers without human verification

## Acceptance Criteria

- A product can be created with mandatory identifiers.
- A device variant can be added to a product.
- Claims and risks can be linked to a product.
- Product data appears in generated report sections.

## Open Questions

- Should reprocessing information be part of Product or a separate domain?
- How to model kit products containing multiple IVD components?
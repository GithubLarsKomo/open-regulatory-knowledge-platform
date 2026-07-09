"""Domain models for regulatory objects — Product, Claim, Evidence.

These models define the structured payload schemas stored inside
the generic RegulatoryObject / ObjectVersion system.

Each domain model is a Pydantic BaseModel that gets serialized
as the `payload_json` column in `object_version`.
"""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Product domain
# ---------------------------------------------------------------------------

class ProductPayload(BaseModel):
    """Payload for a Product regulatory object (REQ-PROD-0001..0007)."""
    product_id: str = Field(..., description="Business key")
    name: str = Field(..., description="Product name")
    description: Optional[str] = Field(None, description="Product description")
    intended_purpose: Optional[str] = Field(None, description="Intended purpose statement")
    target_population: Optional[str] = Field(None, description="Target patient population")
    basic_udi_di: Optional[str] = Field(None, description="Basic UDI-DI per EU IVDR/MDR")
    gmdn_code: Optional[str] = Field(None, description="GMDN code")
    ivr_code: Optional[str] = Field(None, description="IVR code (IVDR)")
    manufacturer_name: Optional[str] = Field(None, description="Legal manufacturer")
    manufacturer_srn: Optional[str] = Field(None, description="Manufacturer SRN number")
    notified_body: Optional[str] = Field(None, description="Notified body reference")
    clinical_indications: Optional[str] = Field(None, description="Clinical indications")
    regulations: List[str] = Field(default_factory=list, description="Applicable regulations (e.g. EU 2017/746)")


class DevicePayload(BaseModel):
    """Payload for a Device variant linked to a Product."""
    device_id: str = Field(..., description="Business key")
    product_uuid: str = Field(..., description="Parent product UUID hex")
    name: str = Field(..., description="Device variant name")
    udi_di: Optional[str] = Field(None, description="UDI-DI")
    description: Optional[str] = Field(None, description="Device variant description")


# ---------------------------------------------------------------------------
# Claim domain
# ---------------------------------------------------------------------------

class ClaimPayload(BaseModel):
    """Payload for a Claim regulatory object (REQ-CLAIM-0001..0006)."""
    claim_type: str = Field(..., description="regulatory/clinical/analytical/performance/safety/marketing")
    jurisdiction: str = Field(..., description="EU/US/UK/CH/etc.")
    language: str = Field(..., description="ISO language code (e.g. en, de, fr)")
    wording: str = Field(..., description="Claim text content")
    product_uuid: Optional[str] = Field(None, description="Linked product UUID hex")
    evidence_links: List[str] = Field(default_factory=list, description="Evidence UUIDs linked to this claim")


class ClaimEvidenceLink(BaseModel):
    """A link between a Claim and an Evidence item."""
    claim_uuid: str = Field(..., description="Claim UUID hex")
    evidence_uuid: str = Field(..., description="Evidence UUID hex")
    link_type: str = Field(default="supports", description="supports/contradicts")
    justification: Optional[str] = Field(None, description="Optional justification if no evidence")


# ---------------------------------------------------------------------------
# Evidence domain
# ---------------------------------------------------------------------------

class EvidencePayload(BaseModel):
    """Payload for an Evidence regulatory object (REQ-EVID-0001..0008)."""
    evidence_type: str = Field(
        ...,
        description="literature_reference|clinical_data|analytical_data|scientific_validity|historical_data|standards_reference|internal_report",
    )
    title: str = Field(..., description="Title of evidence")
    source_reference: Optional[str] = Field(None, description="PMID, DOI, URL or internal ref")
    author: Optional[str] = Field(None, description="Author or organization")
    publication_date: Optional[date] = Field(None, description="Publication or issue date")
    journal: Optional[str] = Field(None, description="Journal or source name")
    version: Optional[str] = Field(None, description="Version identifier")
    quality_rating: Optional[str] = Field(None, description="high/medium/low")
    quality_notes: Optional[str] = Field(None, description="Assessment notes")
    checksum: Optional[str] = Field(None, description="SHA-256 of attached file")
    product_uuid: Optional[str] = Field(None, description="Linked product UUID hex")
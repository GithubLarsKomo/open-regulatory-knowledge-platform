"""Domain services for regulatory objects."""

from typing import Any, Dict, List, Optional, Tuple

from orkp.db.models import RegulatoryObject
from orkp.db.repository import RegulatoryObjectRepository


class DomainService:
    """
    Base class for domain-specific services.

    Each domain service wraps a RegulatoryObjectRepository and provides
    type-safe create/read/update operations for a specific object_type.
    """

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    @property
    def object_type(self) -> str:
        """Override in subclasses to set the object type string."""
        raise NotImplementedError

    def create(self, payload: Dict[str, Any], owner_user_id: str) -> Tuple[RegulatoryObject, Any]:
        """Create a new domain object. Returns (regulatory_object, version)."""
        return self.repo.create_object(
            object_type=self.object_type,
            payload=payload,
            owner_user_id=owner_user_id,
            created_by=owner_user_id,
        )

    def get(self, uuid_hex: str) -> Optional[RegulatoryObject]:
        """Get a domain object by UUID hex."""
        return self.repo.get_by_uuid_hex(uuid_hex)

    def get_with_payload(self, uuid_hex: str) -> Optional[Dict[str, Any]]:
        """Get a domain object with its current payload."""
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            return None
        version = self.repo.get_version(obj.object_uuid, obj.current_version)
        payload = version.payload_json if version else {}
        return {
            "object_uuid": obj.uuid_hex,
            "object_type": obj.object_type,
            "current_version": obj.current_version,
            "lifecycle_state": obj.lifecycle_state,
            "owner_user_id": obj.owner_user_id,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
            "payload": payload,
        }

    def list(self, limit: int = 100, offset: int = 0) -> List[RegulatoryObject]:
        """List all domain objects."""
        return self.repo.list_objects(
            object_type=self.object_type,
            limit=limit,
            offset=offset,
        )

    def update_payload(self, uuid_hex: str, payload: Dict[str, Any], created_by: str) -> Optional[Dict[str, Any]]:
        """Create a new version with updated payload."""
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            return None
        version = self.repo.create_version(obj.object_uuid, payload, created_by)
        if version is None:
            return None
        self.repo.session.commit()
        return self.get_with_payload(uuid_hex)

    def submit_for_review(self, uuid_hex: str, actor_user_id: str) -> bool:
        """Submit a draft object for review."""
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            return False
        result = self.repo.transition_state(obj.object_uuid, 'in_review', actor_user_id)
        if result:
            self.repo.session.commit()
        return result

    def approve(self, uuid_hex: str, approver_user_id: str, comments: Optional[str] = None) -> bool:
        """Approve an in-review object."""
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            return False
        result = self.repo.transition_state(obj.object_uuid, 'approved', approver_user_id, comments)
        if result:
            self.repo.session.commit()
        return result

    def reject(self, uuid_hex: str, reviewer_user_id: str, comments: str) -> bool:
        """Reject an in-review object with comments."""
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            return False
        result = self.repo.transition_state(obj.object_uuid, 'rejected', reviewer_user_id, comments)
        if result:
            self.repo.session.commit()
        return result

    def soft_delete(self, uuid_hex: str, actor_user_id: str) -> bool:
        """Soft-delete a domain object."""
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            return False
        result = self.repo.soft_delete(obj.object_uuid, actor_user_id)
        if result:
            self.repo.session.commit()
        return result


# ---------------------------------------------------------------------------
# Product Service
# ---------------------------------------------------------------------------

class ProductService(DomainService):
    """Domain service for Product objects."""

    @property
    def object_type(self) -> str:
        return 'product'


# ---------------------------------------------------------------------------
# Claim Service
# ---------------------------------------------------------------------------

class ClaimService(DomainService):
    """Domain service for Claim objects."""

    @property
    def object_type(self) -> str:
        return 'claim'

    def link_evidence(self, claim_uuid_hex: str, evidence_uuid_hex: str, link_type: str = 'supports') -> bool:
        """
        Link evidence to a claim by adding the evidence UUID to the claim's payload.

        REQ-CLAIM-0003: Each claim shall be linked to supporting evidence.
        """
        claim_data = self.get_with_payload(claim_uuid_hex)
        if claim_data is None:
            return False

        payload = claim_data['payload']
        evidence_links = payload.get('evidence_links', [])
        if evidence_uuid_hex not in evidence_links:
            evidence_links.append(evidence_uuid_hex)
            payload['evidence_links'] = evidence_links

        result = self.update_payload(
            claim_uuid_hex,
            payload,
            created_by=claim_data['owner_user_id'] or 'system',
        )
        return result is not None

    def check_evidence_coverage(self, uuid_hex: str) -> Dict[str, Any]:
        """
        Check if a claim has sufficient evidence for approval.

        REQ-CLAIM-0006: A claim shall not be approved without at least one evidence link.
        """
        claim_data = self.get_with_payload(uuid_hex)
        if claim_data is None:
            return {"exists": False, "has_evidence": False}

        payload = claim_data['payload']
        evidence_links = payload.get('evidence_links', [])
        has_evidence = len(evidence_links) > 0

        return {
            "exists": True,
            "has_evidence": has_evidence,
            "evidence_count": len(evidence_links),
            "approvable": has_evidence,
            "reason": None if has_evidence else "No evidence linked to this claim",
        }


# ---------------------------------------------------------------------------
# Evidence Service
# ---------------------------------------------------------------------------

class EvidenceService(DomainService):
    """Domain service for Evidence objects."""

    @property
    def object_type(self) -> str:
        return 'evidence'
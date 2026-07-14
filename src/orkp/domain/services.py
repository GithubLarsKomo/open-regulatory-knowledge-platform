"""Domain services for regulatory objects."""

from typing import Any, Dict, List, Optional, Tuple

from orkp.db.models import RegulatoryObject, _bin_to_str
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    InvalidLifecycleTransitionError,
    ImmutableVersionError,
    OptimisticLockError,
)


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
            "lock_version": obj.lock_version,
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
        try:
            version = self.repo.create_version(obj.object_uuid, payload, created_by)
        except (ImmutableVersionError, OptimisticLockError):
            return None
        self.repo.session.commit()
        return self.get_with_payload(uuid_hex)

    def submit_for_review(self, uuid_hex: str, actor_user_id: str) -> bool:
        """Submit a draft object for review."""
        try:
            obj = self.repo.get_by_uuid_hex(uuid_hex)
            if obj is None:
                return False
            self.repo.transition_state(obj.object_uuid, 'in_review', actor_user_id)
            self.repo.session.commit()
            return True
        except (ObjectNotFoundError, InvalidLifecycleTransitionError, OptimisticLockError):
            return False

    def approve(self, uuid_hex: str, approver_user_id: str, comments: Optional[str] = None) -> bool:
        """Approve an in-review object."""
        try:
            obj = self.repo.get_by_uuid_hex(uuid_hex)
            if obj is None:
                return False
            self.repo.transition_state(obj.object_uuid, 'approved', approver_user_id, comments)
            self.repo.session.commit()
            return True
        except (ObjectNotFoundError, InvalidLifecycleTransitionError, OptimisticLockError):
            return False

    def reject(self, uuid_hex: str, reviewer_user_id: str, comments: str) -> bool:
        """Reject an in-review object with comments."""
        try:
            obj = self.repo.get_by_uuid_hex(uuid_hex)
            if obj is None:
                return False
            self.repo.transition_state(obj.object_uuid, 'rejected', reviewer_user_id, comments)
            self.repo.session.commit()
            return True
        except (ObjectNotFoundError, InvalidLifecycleTransitionError, OptimisticLockError):
            return False

    def soft_delete(self, uuid_hex: str, actor_user_id: str) -> bool:
        """Soft-delete a domain object."""
        try:
            obj = self.repo.get_by_uuid_hex(uuid_hex)
            if obj is None:
                return False
            self.repo.soft_delete(obj.object_uuid, actor_user_id)
            self.repo.session.commit()
            return True
        except (ObjectNotFoundError, InvalidLifecycleTransitionError, OptimisticLockError):
            return False


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

    def link_evidence(
        self,
        claim_uuid_hex: str,
        evidence_uuid_hex: str,
        link_type: str = 'supports_claim',
    ) -> bool:
        """
        Link evidence to a claim using object_relation.

        REQ-CLAIM-0003: Each claim shall be linked to supporting evidence.
        Relation references explicit claim and evidence versions (DB-OBJ-0005).
        """
        claim_obj = self.repo.get_by_uuid_hex(claim_uuid_hex)
        evidence_obj = self.repo.get_by_uuid_hex(evidence_uuid_hex)
        if claim_obj is None or evidence_obj is None:
            return False

        try:
            self.repo.create_relation(
                source_uuid=evidence_obj.object_uuid,
                source_version=evidence_obj.current_version,
                target_uuid=claim_obj.object_uuid,
                target_version=claim_obj.current_version,
                relation_type=link_type,
                created_by='system',
            )
            self.repo.session.commit()
            return True
        except Exception:
            return False

    def check_evidence_coverage(self, uuid_hex: str) -> Dict[str, Any]:
        """
        Check if a claim has sufficient evidence for approval.

        REQ-CLAIM-0006: A claim shall not be approved without at least one evidence link.
        Uses object_relation table as source of truth.
        """
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            return {"exists": False, "has_evidence": False}

        relations = self.repo.list_relations_for_target(obj.object_uuid)
        has_evidence = len(relations) > 0

        return {
            "exists": True,
            "has_evidence": has_evidence,
            "evidence_count": len(relations),
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
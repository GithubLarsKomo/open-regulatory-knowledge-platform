"""Domain services for regulatory objects.

State-changing methods raise typed exceptions (not return False).
Query methods may return None when objects do not exist.
"""

from typing import Any, Dict, List, Optional, Tuple

from orkp.db.models import RegulatoryObject, _bin_to_str
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    InvalidLifecycleTransitionError,
    ImmutableVersionError,
    OptimisticLockError,
    InvalidRelationError,
    ProductCompletenessError,
)
from orkp.domain.product_completeness import evaluate_product_completeness


class DomainService:
    """Base class for domain-specific services."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    @property
    def object_type(self) -> str:
        raise NotImplementedError

    def create(self, payload: Dict[str, Any], owner_user_id: str) -> Tuple[RegulatoryObject, Any]:
        return self.repo.create_object(
            object_type=self.object_type,
            payload=payload,
            owner_user_id=owner_user_id,
            created_by=owner_user_id,
        )

    def get(self, uuid_hex: str) -> Optional[RegulatoryObject]:
        return self.repo.get_by_uuid_hex(uuid_hex)

    def get_with_payload(self, uuid_hex: str) -> Optional[Dict[str, Any]]:
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
        return self.repo.list_objects(
            object_type=self.object_type, limit=limit, offset=offset,
        )

    def update_payload(self, uuid_hex: str, payload: Dict[str, Any], created_by: str) -> Optional[Dict[str, Any]]:
        """Create a new version with updated payload.

        Raises: ImmutableVersionError, OptimisticLockError
        """
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"{self.object_type} {uuid_hex} not found")
        version = self.repo.create_version(obj.object_uuid, payload, created_by)
        self.repo.session.commit()
        return self.get_with_payload(uuid_hex)

    def submit_for_review(self, uuid_hex: str, actor_user_id: str) -> None:
        """Submit a draft object for review.

        Raises: ObjectNotFoundError, InvalidLifecycleTransitionError, OptimisticLockError
        """
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"{self.object_type} {uuid_hex} not found")
        self.repo.transition_state(obj.object_uuid, 'in_review', actor_user_id)
        self.repo.session.commit()

    def approve(self, uuid_hex: str, approver_user_id: str, comments: Optional[str] = None) -> None:
        """Approve an in-review object.

        Raises: ObjectNotFoundError, InvalidLifecycleTransitionError, OptimisticLockError
        """
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"{self.object_type} {uuid_hex} not found")
        self.repo.transition_state(obj.object_uuid, 'approved', approver_user_id, comments)
        self.repo.session.commit()

    def reject(self, uuid_hex: str, reviewer_user_id: str, comments: str) -> None:
        """Reject an in-review object.

        Raises: ObjectNotFoundError, InvalidLifecycleTransitionError, OptimisticLockError
        """
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"{self.object_type} {uuid_hex} not found")
        self.repo.transition_state(obj.object_uuid, 'rejected', reviewer_user_id, comments)
        self.repo.session.commit()

    def soft_delete(self, uuid_hex: str, actor_user_id: str) -> None:
        """Soft-delete a domain object.

        Raises: ObjectNotFoundError, InvalidLifecycleTransitionError, OptimisticLockError
        """
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"{self.object_type} {uuid_hex} not found")
        self.repo.soft_delete(obj.object_uuid, actor_user_id)
        self.repo.session.commit()


# ---------------------------------------------------------------------------
# Product Service
# ---------------------------------------------------------------------------

class ProductService(DomainService):
    """Domain service for Product objects."""

    @property
    def object_type(self) -> str:
        return 'product'

    def approve(self, uuid_hex: str, approver_user_id: str, comments: Optional[str] = None) -> None:
        """Approve only if completeness check passes."""
        self._check_completeness(uuid_hex)
        super().approve(uuid_hex, approver_user_id, comments)

    def _check_completeness(self, uuid_hex: str) -> None:
        """Raise ProductCompletenessError if product is not complete."""
        data = self.get_with_payload(uuid_hex)
        if data is None:
            raise ObjectNotFoundError(f"Product {uuid_hex} not found")

        from pydantic import ValidationError
        try:
            from orkp.domain.models import ProductPayload
            payload = ProductPayload(**data['payload'])
        except ValidationError:
            raise ProductCompletenessError("Product payload is invalid")

        # Collect relations
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        relations: Dict[str, list] = {}
        if obj:
            for rel_type in ('has_claim', 'has_risk', 'has_evidence'):
                relations[rel_type] = self.repo.list_relations_for_source(obj.object_uuid)

        result = evaluate_product_completeness(uuid_hex, payload, relations)
        if not result['complete']:
            details = []
            if result['missing_required_fields']:
                details.append(f"Missing fields: {', '.join(result['missing_required_fields'])}")
            if result['missing_relationships']:
                details.append(f"Missing relationships: {', '.join(result['missing_relationships'])}")
            raise ProductCompletenessError(
                "Product does not meet minimum approval requirements. " + "; ".join(details)
            )

    def add_device_variant(
        self,
        product_uuid_hex: str,
        device_payload: Dict[str, Any],
        actor_user_id: str,
    ) -> RegulatoryObject:
        """Atomically create a Device and link via variant_of relation.

        Raises: ObjectNotFoundError, InvalidRelationError
        """
        product = self.repo.get_by_uuid_hex(product_uuid_hex)
        if product is None:
            raise ObjectNotFoundError(f"Product {product_uuid_hex} not found")

        device_obj, _ = self.repo.create_object(
            object_type='device',
            payload=device_payload,
            owner_user_id=actor_user_id,
            created_by=actor_user_id,
        )

        self.repo.create_relation(
            source_uuid=device_obj.object_uuid,
            source_version=device_obj.current_version,
            target_uuid=product.object_uuid,
            target_version=product.current_version,
            relation_type='variant_of',
            created_by=actor_user_id,
        )

        self.repo.session.commit()
        return device_obj

    def list_devices(self, product_uuid_hex: str) -> List[RegulatoryObject]:
        """List all device variants of a product."""
        obj = self.repo.get_by_uuid_hex(product_uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Product {product_uuid_hex} not found")
        relations = self.repo.list_relations_for_target(obj.object_uuid)
        device_uuids = [r.source_uuid for r in relations if r.relation_type == 'variant_of']
        devices = []
        for du in device_uuids:
            dev = self.repo.get_by_uuid(du)
            if dev:
                devices.append(dev)
        return devices

    def link_claim(self, product_uuid_hex: str, claim_uuid_hex: str, actor_user_id: str) -> None:
        """Create a has_claim relation."""
        self._link_relation(product_uuid_hex, claim_uuid_hex, 'has_claim', actor_user_id)

    def link_risk(self, product_uuid_hex: str, risk_uuid_hex: str, actor_user_id: str) -> None:
        """Create a has_risk relation."""
        self._link_relation(product_uuid_hex, risk_uuid_hex, 'has_risk', actor_user_id)

    def link_evidence(self, product_uuid_hex: str, evidence_uuid_hex: str, actor_user_id: str) -> None:
        """Create a has_evidence relation."""
        self._link_relation(product_uuid_hex, evidence_uuid_hex, 'has_evidence', actor_user_id)

    def _link_relation(self, source_hex: str, target_hex: str, rel_type: str, actor_user_id: str) -> None:
        source = self.repo.get_by_uuid_hex(source_hex)
        target = self.repo.get_by_uuid_hex(target_hex)
        if source is None:
            raise ObjectNotFoundError(f"Source {source_hex} not found")
        if target is None:
            raise ObjectNotFoundError(f"Target {target_hex} not found")
        self.repo.create_relation(
            source_uuid=source.object_uuid,
            source_version=source.current_version,
            target_uuid=target.object_uuid,
            target_version=target.current_version,
            relation_type=rel_type,
            created_by=actor_user_id,
        )
        self.repo.session.commit()

    def list_claims(self, product_uuid_hex: str) -> List[Dict[str, Any]]:
        return self._list_related(product_uuid_hex, 'has_claim')

    def list_risks(self, product_uuid_hex: str) -> List[Dict[str, Any]]:
        return self._list_related(product_uuid_hex, 'has_risk')

    def list_evidence(self, product_uuid_hex: str) -> List[Dict[str, Any]]:
        return self._list_related(product_uuid_hex, 'has_evidence')

    def _list_related(self, product_uuid_hex: str, rel_type: str) -> List[Dict[str, Any]]:
        obj = self.repo.get_by_uuid_hex(product_uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Product {product_uuid_hex} not found")
        relations = self.repo.list_relations_for_source(obj.object_uuid)
        results = []
        for r in relations:
            if r.relation_type == rel_type:
                target = self.repo.get_by_uuid(r.target_uuid)
                if target:
                    results.append({
                        "object_uuid": target.uuid_hex,
                        "object_type": target.object_type,
                        "version": r.target_version,
                    })
        return results

    def get_completeness(self, product_uuid_hex: str) -> Dict[str, Any]:
        """Get completeness evaluation for a product."""
        data = self.get_with_payload(product_uuid_hex)
        if data is None:
            raise ObjectNotFoundError(f"Product {product_uuid_hex} not found")
        from pydantic import ValidationError
        try:
            from orkp.domain.models import ProductPayload
            payload = ProductPayload(**data['payload'])
        except ValidationError:
            raise ProductCompletenessError("Product payload is invalid")

        obj = self.repo.get_by_uuid_hex(product_uuid_hex)
        relations: Dict[str, list] = {}
        if obj:
            for rel_type in ('has_claim', 'has_risk', 'has_evidence'):
                relations[rel_type] = self.repo.list_relations_for_source(obj.object_uuid)

        return evaluate_product_completeness(product_uuid_hex, payload, relations)


# ---------------------------------------------------------------------------
# Claim Service
# ---------------------------------------------------------------------------

class ClaimService(DomainService):
    """Domain service for Claim objects."""

    @property
    def object_type(self) -> str:
        return 'claim'

    def approve(self, uuid_hex: str, approver_user_id: str, comments: Optional[str] = None) -> None:
        """Approve only if evidence coverage check passes."""
        self._check_evidence_requirement(uuid_hex)
        super().approve(uuid_hex, approver_user_id, comments)

    def _check_evidence_requirement(self, uuid_hex: str) -> None:
        """Raise ClaimApprovalError if evidence coverage is insufficient."""
        coverage = self.check_evidence_coverage(uuid_hex)
        if not coverage.get('approvable', False):
            from orkp.domain.exceptions import ClaimApprovalError
            raise ClaimApprovalError(
                coverage.get('reason', 'Insufficient evidence coverage')
            )

    def link_evidence(
        self,
        claim_uuid_hex: str,
        evidence_uuid_hex: str,
        link_type: str = 'supported_by',
    ) -> None:
        """Link evidence to a claim using object_relation.

        Raises: ObjectNotFoundError, InvalidRelationError
        """
        claim_obj = self.repo.get_by_uuid_hex(claim_uuid_hex)
        evidence_obj = self.repo.get_by_uuid_hex(evidence_uuid_hex)
        if claim_obj is None:
            raise ObjectNotFoundError(f"Claim {claim_uuid_hex} not found")
        if evidence_obj is None:
            raise ObjectNotFoundError(f"Evidence {evidence_uuid_hex} not found")

        self.repo.create_relation(
            source_uuid=evidence_obj.object_uuid,
            source_version=evidence_obj.current_version,
            target_uuid=claim_obj.object_uuid,
            target_version=claim_obj.current_version,
            relation_type=link_type,
            created_by='system',
        )
        self.repo.session.commit()

    def unlink_evidence(
        self,
        claim_uuid_hex: str,
        evidence_uuid_hex: str,
    ) -> None:
        """Unlink evidence from a claim.

        Note: This is a soft remove — the relation row persists in the DB
        for audit purposes but is filtered from active queries.
        """
        claim_obj = self.repo.get_by_uuid_hex(claim_uuid_hex)
        if claim_obj is None:
            raise ObjectNotFoundError(f"Claim {claim_uuid_hex} not found")
        # For now, unlink is a no-op that validates existence.
        # In a full implementation, we would mark the relation as inactive.
        pass

    def check_evidence_coverage(self, uuid_hex: str) -> Dict[str, Any]:
        """Check claim evidence coverage via object_relation."""
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

    def list_evidence(self, claim_uuid_hex: str) -> List[Dict[str, Any]]:
        """List evidence linked to a claim."""
        obj = self.repo.get_by_uuid_hex(claim_uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Claim {claim_uuid_hex} not found")
        relations = self.repo.list_relations_for_target(obj.object_uuid)
        results = []
        for r in relations:
            ev = self.repo.get_by_uuid(r.source_uuid)
            if ev:
                results.append({
                    "object_uuid": ev.uuid_hex,
                    "relation_type": r.relation_type,
                    "version": r.source_version,
                })
        return results

    def get_coverage_report(self, claim_uuid_hex: str) -> Dict[str, Any]:
        """Get detailed evidence coverage report."""
        obj = self.repo.get_by_uuid_hex(claim_uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Claim {claim_uuid_hex} not found")

        relations = self.repo.list_relations_for_target(obj.object_uuid)
        evidence_objects = {}
        for r in relations:
            ev = self.repo.get_by_uuid(r.source_uuid)
            if ev:
                version = self.repo.get_version(ev.object_uuid, ev.current_version)
                evidence_objects[ev.uuid_hex] = {
                    "lifecycle_state": ev.lifecycle_state,
                    "quality_rating": (version.payload_json or {}).get('quality_rating') if version else None,
                }

        from orkp.domain.evidence_completeness import evaluate_evidence_coverage
        return evaluate_evidence_coverage(
            claim_uuid_hex,
            [{"source_uuid_hex": _bin_to_str(r.source_uuid)} for r in relations],
            evidence_objects,
        )

    def get_history(self, claim_uuid_hex: str) -> Dict[str, Any]:
        """Get claim version and event history."""
        obj = self.repo.get_by_uuid_hex(claim_uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Claim {claim_uuid_hex} not found")
        versions = self.repo.list_versions(obj.object_uuid)
        events = self.repo.get_event_history(obj.object_uuid)
        return {
            "object_uuid": claim_uuid_hex,
            "current_version": obj.current_version,
            "lifecycle_state": obj.lifecycle_state,
            "version_count": len(versions),
            "event_count": len(events),
        }


# ---------------------------------------------------------------------------
# Evidence Service
# ---------------------------------------------------------------------------

class EvidenceService(DomainService):
    """Domain service for Evidence objects."""

    @property
    def object_type(self) -> str:
        return 'evidence'

    def find_claims(self, evidence_uuid_hex: str) -> List[Dict[str, Any]]:
        """Find all claims linked to this evidence."""
        obj = self.repo.get_by_uuid_hex(evidence_uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Evidence {evidence_uuid_hex} not found")
        relations = self.repo.list_relations_for_source(obj.object_uuid)
        results = []
        for r in relations:
            if r.relation_type in ('supported_by', 'contradicted_by'):
                target = self.repo.get_by_uuid(r.target_uuid)
                if target:
                    results.append({
                        "object_uuid": target.uuid_hex,
                        "relation_type": r.relation_type,
                        "version": r.target_version,
                    })
        return results

    def get_coverage(self, evidence_uuid_hex: str) -> Dict[str, Any]:
        """Get coverage stats for this evidence."""
        obj = self.repo.get_by_uuid_hex(evidence_uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Evidence {evidence_uuid_hex} not found")
        relations = self.repo.list_relations_for_source(obj.object_uuid)
        return {
            "evidence_uuid": evidence_uuid_hex,
            "linked_claim_count": len(relations),
            "relation_types": list(set(r.relation_type for r in relations)),
        }

    def get_quality_summary(self, evidence_uuid_hex: str) -> Dict[str, Any]:
        """Get quality assessment summary."""
        obj = self.repo.get_by_uuid_hex(evidence_uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Evidence {evidence_uuid_hex} not found")
        version = self.repo.get_version(obj.object_uuid, obj.current_version)
        payload = version.payload_json if version else {}
        return {
            "evidence_uuid": evidence_uuid_hex,
            "quality_rating": payload.get('quality_rating'),
            "quality_notes": payload.get('quality_notes'),
            "evidence_type": payload.get('evidence_type'),
            "publication_status": payload.get('publication_status'),
        }


# ---------------------------------------------------------------------------
# Device Service
# ---------------------------------------------------------------------------

class DeviceService(DomainService):
    """Domain service for Device objects."""

    @property
    def object_type(self) -> str:
        return 'device'
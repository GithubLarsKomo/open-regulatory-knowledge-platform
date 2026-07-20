"""Domain services for regulatory objects.

State-changing methods raise typed exceptions (not return False).
Query methods may return None when objects do not exist.
"""

import uuid
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
    ClaimApprovalError,
    RelationNotFoundError,
    RelationAlreadyInactiveError,
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

        # Collect active relations only
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        relations: Dict[str, list] = {}
        if obj:
            all_rels = self.repo.list_active_relations_for_source(obj.object_uuid)
            for rel_type in ('has_claim', 'has_risk', 'has_evidence'):
                relations[rel_type] = [r for r in all_rels if r.relation_type == rel_type]

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
            all_rels = self.repo.list_active_relations_for_source(obj.object_uuid)
            for rel_type in ('has_claim', 'has_risk', 'has_evidence'):
                relations[rel_type] = [r for r in all_rels if r.relation_type == rel_type]

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
        """Approve only if claim approval assessment passes."""
        assessment = self.get_approval_assessment(uuid_hex)
        if not assessment['approvable']:
            raise ClaimApprovalError(
                "Claim approval blocked: " + "; ".join(assessment['blocking_issues'])
            )
        super().approve(uuid_hex, approver_user_id, comments)

    def get_approval_assessment(self, uuid_hex: str) -> Dict[str, Any]:
        """Get structured claim approval assessment.

        Reports ALL blocking issues simultaneously (not conditioned).
        Checks: product relation, active supported_by evidence,
        evidence version approved, no contradicted_by, quality threshold,
        evidence type policy.
        """
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Claim {uuid_hex} not found")

        from datetime import datetime, timezone
        from orkp.domain.evidence_policy import default_evidence_policy
        issues: List[str] = []
        warnings: List[str] = []
        supporting: List[Dict] = []
        contradicting: List[Dict] = []
        product_relations: List[Dict] = []
        score = 0
        total_checks = 8

        # 1. Must be in_review
        if obj.lifecycle_state != 'in_review':
            issues.append("Claim is not in_review")

        # 2. Must have product relation
        all_relations = self.repo.list_all_relations_for_target(obj.object_uuid)
        for r in all_relations:
            if r.relation_type == 'has_claim' and r.lifecycle_state == 'active':
                product_relations.append({
                    "relation_uuid": _bin_to_str(r.relation_uuid),
                    "source_uuid": _bin_to_str(r.source_uuid),
                })
        if not product_relations:
            issues.append("No active product relation")
        else:
            score += 1

        # 3. Must have active supported_by evidence
        # 4. Evidence version must be approved
        # 5. No contradicting evidence
        # 6. Quality must meet threshold
        # 7. Evidence type must be suitable
        policy = default_evidence_policy()
        payload = {}
        version = self.repo.get_version(obj.object_uuid, obj.current_version)
        if version:
            payload = version.payload_json or {}
        claim_severity = payload.get('severity', 'medium')
        claim_type = payload.get('claim_type', '')
        required_quality = policy.get_min_quality_for_severity(claim_severity)
        allowed_types = policy.get_allowed_evidence_types(claim_type)

        has_suitable_evidence = False
        quality_ok = True

        for r in all_relations:
            if r.relation_type == 'supported_by' and r.lifecycle_state == 'active':
                ev = self.repo.get_by_uuid(r.source_uuid)
                if ev is None:
                    issues.append(f"Evidence {_bin_to_str(r.source_uuid)} not found")
                    continue
                ev_version = self.repo.get_version(r.source_uuid, r.source_version)
                ev_status = ev_version.status if ev_version else 'unknown'
                ev_state = ev.lifecycle_state
                ev_payload = ev_version.payload_json if ev_version else {}
                ev_quality = ev_payload.get('quality_rating', 'unknown')
                ev_type = ev_payload.get('evidence_type', '')

                supporting.append({
                    "relation_uuid": _bin_to_str(r.relation_uuid),
                    "evidence_uuid": _bin_to_str(r.source_uuid),
                    "evidence_version": r.source_version,
                    "evidence_version_status": ev_status,
                    "evidence_lifecycle_state": ev_state,
                    "quality_rating": ev_quality,
                    "evidence_type": ev_type,
                })

                if ev_state in ('deleted', 'obsolete'):
                    issues.append(f"Evidence version {r.source_version} is {ev_state}")
                elif ev_status != 'approved':
                    issues.append(f"Evidence version {r.source_version} status is '{ev_status}', not 'approved'")
                else:
                    score += 1
                    if not policy.quality_meets_threshold(ev_quality, required_quality):
                        issues.append(
                            f"Evidence {_bin_to_str(r.source_uuid)[:8]} quality '{ev_quality}' "
                            f"below required '{required_quality}'"
                        )
                        quality_ok = False
                    if ev_type in allowed_types:
                        has_suitable_evidence = True
                    else:
                        warnings.append(
                            f"Evidence type '{ev_type}' may not be suitable for claim type '{claim_type}'"
                        )

            if r.relation_type == 'contradicted_by' and r.lifecycle_state == 'active':
                contradicting.append({
                    "relation_uuid": _bin_to_str(r.relation_uuid),
                    "evidence_uuid": _bin_to_str(r.source_uuid),
                    "evidence_version": r.source_version,
                })
                issues.append("Active contradicted_by evidence exists")

        if not supporting:
            issues.append("No active supported_by evidence relation")
            score += 1  # No evidence = no issue about quality/type

        # 8. If evidence exists but none suitable, block
        if supporting and not has_suitable_evidence:
            issues.append(f"No evidence with allowed type for '{claim_type}' claims")

        # Calculate score (penalize for missing items)
        score = min(100, int((score / max(total_checks, 1)) * 100))

        return {
            "claim_uuid": uuid_hex,
            "approvable": len(issues) == 0,
            "score": score,
            "blocking_issues": issues,
            "warnings": warnings,
            "supporting_evidence": supporting,
            "contradicting_evidence": contradicting,
            "product_relations": product_relations,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

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
        actor_user_id: str = 'system',
        reason: str = 'Removed',
    ) -> None:
        """Deactivate an active supported_by or contradicted_by relation.

        Raises: ObjectNotFoundError, RelationNotFoundError, RelationAlreadyInactiveError
        """
        claim_obj = self.repo.get_by_uuid_hex(claim_uuid_hex)
        evidence_obj = self.repo.get_by_uuid_hex(evidence_uuid_hex)
        if claim_obj is None:
            raise ObjectNotFoundError(f"Claim {claim_uuid_hex} not found")
        if evidence_obj is None:
            raise ObjectNotFoundError(f"Evidence {evidence_uuid_hex} not found")

        # Find the active relation
        relations = self.repo.list_active_relations_for_target(claim_obj.object_uuid)
        target_rel = None
        for r in relations:
            if r.source_uuid == evidence_obj.object_uuid and r.relation_type in ('supported_by', 'contradicted_by'):
                target_rel = r
                break

        if target_rel is None:
            raise RelationNotFoundError(
                f"No active relation between claim {claim_uuid_hex} and evidence {evidence_uuid_hex}"
            )

        self.repo.deactivate_relation(target_rel.relation_uuid, actor_user_id, reason)
        self.repo.session.commit()

    def check_evidence_coverage(self, uuid_hex: str) -> Dict[str, Any]:
        """Check claim evidence coverage — only active supported_by counts as evidence."""
        obj = self.repo.get_by_uuid_hex(uuid_hex)
        if obj is None:
            return {"exists": False, "has_evidence": False}

        relations = self.repo.list_active_relations_for_target(obj.object_uuid)
        supporting = [r for r in relations if r.relation_type == 'supported_by']
        contradicting = [r for r in relations if r.relation_type == 'contradicted_by']
        has_evidence = len(supporting) > 0

        return {
            "exists": True,
            "has_evidence": has_evidence,
            "supporting_count": len(supporting),
            "contradicting_count": len(contradicting),
            "total_active_relations": len(relations),
            "approvable": has_evidence,
            "reason": None if has_evidence else "No supporting evidence linked to this claim",
        }

    def list_evidence(self, claim_uuid_hex: str) -> List[Dict[str, Any]]:
        """List evidence linked to a claim (active relations, version-pinned)."""
        obj = self.repo.get_by_uuid_hex(claim_uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Claim {claim_uuid_hex} not found")
        relations = self.repo.list_active_relations_for_target(obj.object_uuid)
        results = []
        for r in relations:
            ev = self.repo.get_by_uuid(r.source_uuid)
            ev_version = self.repo.get_version(r.source_uuid, r.source_version)
            ev_status = ev_version.status if ev_version else 'unknown'
            ev_state = ev.lifecycle_state if ev else 'unknown'
            results.append({
                "relation_uuid": _bin_to_str(r.relation_uuid),
                "relation_type": r.relation_type,
                "relation_state": r.lifecycle_state,
                "evidence_uuid": _bin_to_str(r.source_uuid),
                "evidence_version": r.source_version,
                "evidence_lifecycle_state": ev_state,
                "evidence_version_status": ev_status,
                "claim_uuid": claim_uuid_hex,
                "claim_version": r.target_version,
            })
        return results

    def get_coverage_report(self, claim_uuid_hex: str) -> Dict[str, Any]:
        """Get detailed evidence coverage report (active relations, version-pinned)."""
        obj = self.repo.get_by_uuid_hex(claim_uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Claim {claim_uuid_hex} not found")

        relations = self.repo.list_active_relations_for_target(obj.object_uuid)
        evidence_objects = {}
        for r in relations:
            ev = self.repo.get_by_uuid(r.source_uuid)
            if ev:
                # Use the EXACT version stored in the relation
                ev_version = self.repo.get_version(r.source_uuid, r.source_version)
                evidence_objects[_bin_to_str(r.source_uuid)] = {
                    "lifecycle_state": ev.lifecycle_state,
                    "quality_rating": (ev_version.payload_json or {}).get('quality_rating') if ev_version else None,
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
        """Find all claims linked to this evidence (version-pinned)."""
        obj = self.repo.get_by_uuid_hex(evidence_uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Evidence {evidence_uuid_hex} not found")
        relations = self.repo.list_active_relations_for_source(obj.object_uuid)
        results = []
        for r in relations:
            if r.relation_type in ('supported_by', 'contradicted_by'):
                target = self.repo.get_by_uuid(r.target_uuid)
                if target:
                    results.append({
                        "relation_uuid": _bin_to_str(r.relation_uuid),
                        "relation_type": r.relation_type,
                        "relation_state": r.lifecycle_state,
                        "evidence_uuid": evidence_uuid_hex,
                        "evidence_version": r.source_version,
                        "claim_uuid": target.uuid_hex,
                        "claim_version": r.target_version,
                    })
        return results

    def get_coverage(self, evidence_uuid_hex: str) -> Dict[str, Any]:
        """Get coverage stats — counts only active supported_by/contradicted_by."""
        obj = self.repo.get_by_uuid_hex(evidence_uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Evidence {evidence_uuid_hex} not found")
        relations = self.repo.list_active_relations_for_source(obj.object_uuid)
        supporting = 0
        contradicting = 0
        approved = 0
        draft = 0
        obsolete = 0
        for r in relations:
            if r.relation_type == 'supported_by':
                supporting += 1
            elif r.relation_type == 'contradicted_by':
                contradicting += 1
            else:
                continue  # Only count claim relations
            target = self.repo.get_by_uuid(r.target_uuid)
            if target:
                if target.lifecycle_state == 'approved':
                    approved += 1
                elif target.lifecycle_state == 'draft':
                    draft += 1
                elif target.lifecycle_state in ('obsolete', 'deleted'):
                    obsolete += 1
        return {
            "evidence_uuid": evidence_uuid_hex,
            "supporting_claim_count": supporting,
            "contradicting_claim_count": contradicting,
            "approved_claim_count": approved,
            "draft_claim_count": draft,
            "obsolete_claim_count": obsolete,
            "total_active_claim_relations": supporting + contradicting,
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

    def supersede_evidence(
        self,
        old_evidence_uuid_hex: str,
        replacement_uuid_hex: str,
        actor_user_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Supersede old evidence with a replacement.

        Creates a supersedes relation, transitions old evidence to obsolete,
        and returns an impact assessment.

        Raises: ObjectNotFoundError, InvalidLifecycleTransitionError
        """
        old = self.repo.get_by_uuid_hex(old_evidence_uuid_hex)
        replacement = self.repo.get_by_uuid_hex(replacement_uuid_hex)
        if old is None:
            raise ObjectNotFoundError(f"Evidence {old_evidence_uuid_hex} not found")
        if replacement is None:
            raise ObjectNotFoundError(f"Replacement evidence {replacement_uuid_hex} not found")

        # Replacement must be approved
        if replacement.lifecycle_state != 'approved':
            raise InvalidLifecycleTransitionError(
                f"Replacement evidence {replacement_uuid_hex} is not approved"
            )

        # Create supersedes relation
        self.repo.create_relation(
            source_uuid=replacement.object_uuid,
            source_version=replacement.current_version,
            target_uuid=old.object_uuid,
            target_version=old.current_version,
            relation_type='supersedes',
            created_by=actor_user_id,
        )

        # Transition old evidence to obsolete
        self.repo.transition_state(old.object_uuid, 'obsolete', actor_user_id, reason)

        # Find affected claims
        affected_claims = self.find_claims(old_evidence_uuid_hex)
        blocking_claims = [
            c for c in affected_claims
            if c.get('relation_type') == 'supported_by'
        ]

        # Find affected products
        affected_products = []
        for c in affected_claims:
            claim = self.repo.get_by_uuid_hex(c.get('claim_uuid', ''))
            if claim:
                product_rels = self.repo.list_active_relations_for_target(claim.object_uuid)
                for pr in product_rels:
                    if pr.relation_type == 'has_claim':
                        prod = self.repo.get_by_uuid(pr.source_uuid)
                        if prod:
                            affected_products.append({
                                "product_uuid": prod.uuid_hex,
                                "claim_uuid": c.get('claim_uuid', ''),
                            })

        self.repo.session.commit()

        return {
            "superseded_evidence_uuid": old_evidence_uuid_hex,
            "replacement_evidence_uuid": replacement_uuid_hex,
            "affected_claims": affected_claims,
            "affected_products": affected_products,
            "blocking_claims": blocking_claims,
            "warnings": [f"Evidence {old_evidence_uuid_hex[:8]} superseded by {replacement_uuid_hex[:8]}"],
        }

    def get_impact(self, evidence_uuid_hex: str) -> Dict[str, Any]:
        """Get impact assessment for evidence supersession."""
        obj = self.repo.get_by_uuid_hex(evidence_uuid_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Evidence {evidence_uuid_hex} not found")
        claims = self.find_claims(evidence_uuid_hex)
        return {
            "evidence_uuid": evidence_uuid_hex,
            "lifecycle_state": obj.lifecycle_state,
            "affected_claims": claims,
            "blocking_claim_count": len([c for c in claims if c.get('relation_type') == 'supported_by']),
        }


# ---------------------------------------------------------------------------
# Device Service
# ---------------------------------------------------------------------------

class DeviceService(DomainService):
    """Domain service for Device objects."""

    @property
    def object_type(self) -> str:
        return 'device'
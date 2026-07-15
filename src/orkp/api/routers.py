"""FastAPI routers for domain-specific endpoints.

Uses typed domain exceptions. The global ORKPError exception handler
in main.py maps exceptions to HTTP status codes.
"""

from typing import Callable, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from orkp.api.schemas import (
    RegulatoryObjectResponse,
    ProductCreateRequest,
    ProductDetailResponse,
    ProductCompletenessResponse,
    DeviceCreateRequest,
)
from orkp.domain.models import ClaimPayload, EvidencePayload, ProductPayload, DevicePayload
from orkp.domain.services import (
    ClaimService,
    EvidenceService,
    ProductService,
    DeviceService,
)
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
from orkp.db.repository import RegulatoryObjectRepository


# ---------------------------------------------------------------------------
# Helper: wrap domain exceptions into HTTP
# ---------------------------------------------------------------------------

def _call_or_404(service_fn):
    """Call a service method; let ORKPError handler deal with it."""
    try:
        return service_fn()
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except (InvalidLifecycleTransitionError, ImmutableVersionError, OptimisticLockError) as e:
        raise HTTPException(status_code=409, detail=e.message)
    except (InvalidRelationError, ProductCompletenessError, ClaimApprovalError) as e:
        raise HTTPException(status_code=422, detail=e.message)
    except (RelationNotFoundError, RelationAlreadyInactiveError) as e:
        raise HTTPException(status_code=409 if isinstance(e, RelationAlreadyInactiveError) else 404, detail=e.message)


# ---------------------------------------------------------------------------
# Product Router
# ---------------------------------------------------------------------------

def create_product_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/products", tags=["Products"])

    def _get_service(repo: RegulatoryObjectRepository = Depends(get_repo)) -> ProductService:
        return ProductService(repo)

    @router.post("", response_model=RegulatoryObjectResponse, status_code=status.HTTP_201_CREATED)
    async def create_product(
        payload: ProductPayload,
        owner_user_id: str = Query(...),
        service: ProductService = Depends(_get_service),
    ):
        obj, version = service.create(payload.model_dump(), owner_user_id)
        service.repo.session.commit()
        return RegulatoryObjectResponse(
            object_uuid=obj.uuid_hex,
            object_type=obj.object_type,
            current_version=obj.current_version,
            lifecycle_state=obj.lifecycle_state,
            owner_user_id=obj.owner_user_id,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    @router.get("", response_model=List[RegulatoryObjectResponse])
    async def list_products(
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        service: ProductService = Depends(_get_service),
    ):
        objects = service.list(limit=limit, offset=offset)
        return [
            RegulatoryObjectResponse(
                object_uuid=obj.uuid_hex, object_type=obj.object_type,
                current_version=obj.current_version, lifecycle_state=obj.lifecycle_state,
                owner_user_id=obj.owner_user_id, created_at=obj.created_at,
                updated_at=obj.updated_at,
            ) for obj in objects
        ]

    @router.get("/{uuid}", response_model=ProductDetailResponse)
    async def get_product(
        uuid: str,
        service: ProductService = Depends(_get_service),
    ):
        data = _call_or_404(lambda: service.get_with_payload(uuid))
        if data is None:
            raise HTTPException(status_code=404, detail="Product not found")
        return ProductDetailResponse(
            object_uuid=data["object_uuid"],
            object_type=data["object_type"],
            current_version=data["current_version"],
            lifecycle_state=data["lifecycle_state"],
            owner_user_id=data["owner_user_id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            payload=data["payload"],
        )

    @router.post("/{uuid}/submit", response_model=dict)
    async def submit_product(
        uuid: str,
        actor_user_id: str = Query(...),
        service: ProductService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.submit_for_review(uuid, actor_user_id))
        return {"status": "submitted_for_review", "uuid": uuid}

    @router.post("/{uuid}/approve", response_model=dict)
    async def approve_product(
        uuid: str,
        actor_user_id: str = Query(...),
        comments: Optional[str] = Query(None),
        service: ProductService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.approve(uuid, actor_user_id, comments))
        return {"status": "approved", "uuid": uuid}

    @router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_product(
        uuid: str,
        actor_user_id: str = Query(...),
        service: ProductService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.soft_delete(uuid, actor_user_id))

    @router.post("/{uuid}/devices", response_model=RegulatoryObjectResponse, status_code=201)
    async def add_device(
        uuid: str,
        payload: DevicePayload,
        actor_user_id: str = Query(...),
        service: ProductService = Depends(_get_service),
    ):
        device = _call_or_404(lambda: service.add_device_variant(uuid, payload.model_dump(), actor_user_id))
        return RegulatoryObjectResponse(
            object_uuid=device.uuid_hex,
            object_type=device.object_type,
            current_version=device.current_version,
            lifecycle_state=device.lifecycle_state,
            owner_user_id=device.owner_user_id,
            created_at=device.created_at,
            updated_at=device.updated_at,
        )

    @router.get("/{uuid}/devices", response_model=List[RegulatoryObjectResponse])
    async def list_device_variants(
        uuid: str,
        service: ProductService = Depends(_get_service),
    ):
        devices = _call_or_404(lambda: service.list_devices(uuid))
        return [
            RegulatoryObjectResponse(
                object_uuid=d.uuid_hex, object_type=d.object_type,
                current_version=d.current_version, lifecycle_state=d.lifecycle_state,
                owner_user_id=d.owner_user_id, created_at=d.created_at,
                updated_at=d.updated_at,
            ) for d in devices
        ]

    @router.post("/{uuid}/claims/{claim_uuid}")
    async def link_claim(
        uuid: str,
        claim_uuid: str,
        actor_user_id: str = Query(...),
        service: ProductService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.link_claim(uuid, claim_uuid, actor_user_id))
        return {"status": "linked", "type": "has_claim"}

    @router.post("/{uuid}/risks/{risk_uuid}")
    async def link_risk(
        uuid: str,
        risk_uuid: str,
        actor_user_id: str = Query(...),
        service: ProductService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.link_risk(uuid, risk_uuid, actor_user_id))
        return {"status": "linked", "type": "has_risk"}

    @router.post("/{uuid}/evidence/{evidence_uuid}")
    async def link_evidence(
        uuid: str,
        evidence_uuid: str,
        actor_user_id: str = Query(...),
        service: ProductService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.link_evidence(uuid, evidence_uuid, actor_user_id))
        return {"status": "linked", "type": "has_evidence"}

    @router.get("/{uuid}/completeness", response_model=ProductCompletenessResponse)
    async def completeness(
        uuid: str,
        service: ProductService = Depends(_get_service),
    ):
        result = _call_or_404(lambda: service.get_completeness(uuid))
        return ProductCompletenessResponse(**result)

    return router


# ---------------------------------------------------------------------------
# Claim Router
# ---------------------------------------------------------------------------

def create_claim_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/claims", tags=["Claims"])

    def _get_service(repo: RegulatoryObjectRepository = Depends(get_repo)) -> ClaimService:
        return ClaimService(repo)

    @router.post("", response_model=RegulatoryObjectResponse, status_code=status.HTTP_201_CREATED)
    async def create_claim(
        payload: ClaimPayload,
        owner_user_id: str = Query(...),
        service: ClaimService = Depends(_get_service),
    ):
        obj, version = service.create(payload.model_dump(), owner_user_id)
        service.repo.session.commit()
        return RegulatoryObjectResponse(
            object_uuid=obj.uuid_hex, object_type=obj.object_type,
            current_version=obj.current_version, lifecycle_state=obj.lifecycle_state,
            owner_user_id=obj.owner_user_id, created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    @router.get("", response_model=List[RegulatoryObjectResponse])
    async def list_claims(
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        service: ClaimService = Depends(_get_service),
    ):
        objects = service.list(limit=limit, offset=offset)
        return [
            RegulatoryObjectResponse(
                object_uuid=obj.uuid_hex, object_type=obj.object_type,
                current_version=obj.current_version, lifecycle_state=obj.lifecycle_state,
                owner_user_id=obj.owner_user_id, created_at=obj.created_at,
                updated_at=obj.updated_at,
            ) for obj in objects
        ]

    @router.get("/{uuid}", response_model=dict)
    async def get_claim(
        uuid: str,
        service: ClaimService = Depends(_get_service),
    ):
        data = service.get_with_payload(uuid)
        if data is None:
            raise HTTPException(status_code=404, detail="Claim not found")
        return data

    @router.post("/{uuid}/link-evidence", response_model=dict)
    async def link_evidence(
        uuid: str,
        evidence_uuid: str = Query(...),
        link_type: str = Query("supported_by"),
        service: ClaimService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.link_evidence(uuid, evidence_uuid, link_type))
        return {"status": "linked", "claim_uuid": uuid, "evidence_uuid": evidence_uuid}

    @router.post("/{uuid}/evidence/{evidence_uuid}")
    async def link_evidence_path(
        uuid: str,
        evidence_uuid: str,
        link_type: str = Query("supported_by"),
        service: ClaimService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.link_evidence(uuid, evidence_uuid, link_type))
        return {"status": "linked", "claim_uuid": uuid, "evidence_uuid": evidence_uuid}

    @router.delete("/{uuid}/evidence/{evidence_uuid}")
    async def unlink_evidence(
        uuid: str,
        evidence_uuid: str,
        actor_user_id: str = Query("system"),
        reason: str = Query("Removed"),
        service: ClaimService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.unlink_evidence(uuid, evidence_uuid, actor_user_id, reason))
        return {"status": "unlinked", "claim_uuid": uuid, "evidence_uuid": evidence_uuid}

    @router.get("/{uuid}/evidence-coverage", response_model=dict)
    async def check_evidence_coverage(
        uuid: str,
        service: ClaimService = Depends(_get_service),
    ):
        result = service.check_evidence_coverage(uuid)
        if not result["exists"]:
            raise HTTPException(status_code=404, detail="Claim not found")
        return result

    @router.get("/{uuid}/coverage", response_model=dict)
    async def coverage_report(
        uuid: str,
        service: ClaimService = Depends(_get_service),
    ):
        return _call_or_404(lambda: service.get_coverage_report(uuid))

    @router.get("/{uuid}/approval-assessment", response_model=dict)
    async def approval_assessment(
        uuid: str,
        service: ClaimService = Depends(_get_service),
    ):
        return _call_or_404(lambda: service.get_approval_assessment(uuid))

    @router.get("/{uuid}/evidence", response_model=List[dict])
    async def list_claim_evidence(
        uuid: str,
        service: ClaimService = Depends(_get_service),
    ):
        return _call_or_404(lambda: service.list_evidence(uuid))

    @router.get("/{uuid}/history", response_model=dict)
    async def claim_history(
        uuid: str,
        service: ClaimService = Depends(_get_service),
    ):
        return _call_or_404(lambda: service.get_history(uuid))

    @router.post("/{uuid}/submit", response_model=dict)
    async def submit_claim(
        uuid: str,
        actor_user_id: str = Query(...),
        service: ClaimService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.submit_for_review(uuid, actor_user_id))
        return {"status": "submitted_for_review", "uuid": uuid}

    @router.post("/{uuid}/approve", response_model=dict)
    async def approve_claim(
        uuid: str,
        actor_user_id: str = Query(...),
        comments: Optional[str] = Query(None),
        service: ClaimService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.approve(uuid, actor_user_id, comments))
        return {"status": "approved", "uuid": uuid}

    @router.post("/{uuid}/reject", response_model=dict)
    async def reject_claim(
        uuid: str,
        actor_user_id: str = Query(...),
        comments: str = Query(...),
        service: ClaimService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.reject(uuid, actor_user_id, comments))
        return {"status": "rejected", "uuid": uuid}

    @router.delete("/{uuid}", status_code=204)
    async def delete_claim(
        uuid: str,
        actor_user_id: str = Query(...),
        service: ClaimService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.soft_delete(uuid, actor_user_id))

    return router


# ---------------------------------------------------------------------------
# Evidence Router
# ---------------------------------------------------------------------------

def create_evidence_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/evidence", tags=["Evidence"])

    def _get_service(repo: RegulatoryObjectRepository = Depends(get_repo)) -> EvidenceService:
        return EvidenceService(repo)

    @router.post("", response_model=RegulatoryObjectResponse, status_code=status.HTTP_201_CREATED)
    async def create_evidence(
        payload: EvidencePayload,
        owner_user_id: str = Query(...),
        service: EvidenceService = Depends(_get_service),
    ):
        obj, _ = service.create(payload.model_dump(), owner_user_id)
        service.repo.session.commit()
        return RegulatoryObjectResponse(
            object_uuid=obj.uuid_hex, object_type=obj.object_type,
            current_version=obj.current_version, lifecycle_state=obj.lifecycle_state,
            owner_user_id=obj.owner_user_id, created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    @router.get("", response_model=List[RegulatoryObjectResponse])
    async def list_evidence(
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        service: EvidenceService = Depends(_get_service),
    ):
        objects = service.list(limit=limit, offset=offset)
        return [
            RegulatoryObjectResponse(
                object_uuid=obj.uuid_hex, object_type=obj.object_type,
                current_version=obj.current_version, lifecycle_state=obj.lifecycle_state,
                owner_user_id=obj.owner_user_id, created_at=obj.created_at,
                updated_at=obj.updated_at,
            ) for obj in objects
        ]

    @router.get("/{uuid}", response_model=dict)
    async def get_evidence(
        uuid: str,
        service: EvidenceService = Depends(_get_service),
    ):
        data = service.get_with_payload(uuid)
        if data is None:
            raise HTTPException(status_code=404, detail="Evidence not found")
        return data

    @router.post("/{uuid}/submit", response_model=dict)
    async def submit_evidence(
        uuid: str,
        actor_user_id: str = Query(...),
        service: EvidenceService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.submit_for_review(uuid, actor_user_id))
        return {"status": "submitted_for_review", "uuid": uuid}

    @router.post("/{uuid}/approve", response_model=dict)
    async def approve_evidence(
        uuid: str,
        actor_user_id: str = Query(...),
        comments: Optional[str] = Query(None),
        service: EvidenceService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.approve(uuid, actor_user_id, comments))
        return {"status": "approved", "uuid": uuid}

    @router.get("/{uuid}/claims", response_model=List[dict])
    async def evidence_claims(
        uuid: str,
        service: EvidenceService = Depends(_get_service),
    ):
        return _call_or_404(lambda: service.find_claims(uuid))

    @router.get("/{uuid}/coverage", response_model=dict)
    async def evidence_coverage(
        uuid: str,
        service: EvidenceService = Depends(_get_service),
    ):
        return _call_or_404(lambda: service.get_coverage(uuid))

    @router.get("/{uuid}/quality", response_model=dict)
    async def evidence_quality(
        uuid: str,
        service: EvidenceService = Depends(_get_service),
    ):
        return _call_or_404(lambda: service.get_quality_summary(uuid))

    @router.post("/{uuid}/supersede/{replacement_uuid}")
    async def supersede_evidence(
        uuid: str,
        replacement_uuid: str,
        actor_user_id: str = Query(...),
        reason: str = Query(...),
        service: EvidenceService = Depends(_get_service),
    ):
        return _call_or_404(lambda: service.supersede_evidence(uuid, replacement_uuid, actor_user_id, reason))

    @router.get("/{uuid}/impact", response_model=dict)
    async def evidence_impact(
        uuid: str,
        service: EvidenceService = Depends(_get_service),
    ):
        return _call_or_404(lambda: service.get_impact(uuid))

    @router.delete("/{uuid}", status_code=204)
    async def delete_evidence(
        uuid: str,
        actor_user_id: str = Query(...),
        service: EvidenceService = Depends(_get_service),
    ):
        _call_or_404(lambda: service.soft_delete(uuid, actor_user_id))

    return router
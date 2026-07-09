"""FastAPI routers for domain-specific endpoints — Product, Claim, Evidence.

These routers are created via factory functions that accept a dependency
callback for getting the repository, enabling testability.
"""

from typing import Callable, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from orkp.api.schemas import RegulatoryObjectResponse
from orkp.domain.models import ClaimPayload, EvidencePayload, ProductPayload
from orkp.domain.services import ClaimService, EvidenceService, ProductService
from orkp.db.repository import RegulatoryObjectRepository


def create_product_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    """Create a Product router with the given dependency injection."""
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
                object_uuid=obj.uuid_hex,
                object_type=obj.object_type,
                current_version=obj.current_version,
                lifecycle_state=obj.lifecycle_state,
                owner_user_id=obj.owner_user_id,
                created_at=obj.created_at,
                updated_at=obj.updated_at,
            )
            for obj in objects
        ]

    @router.get("/{uuid}", response_model=dict)
    async def get_product(
        uuid: str,
        service: ProductService = Depends(_get_service),
    ):
        data = service.get_with_payload(uuid)
        if data is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        return data

    @router.post("/{uuid}/submit", response_model=dict)
    async def submit_product(
        uuid: str,
        actor_user_id: str = Query(...),
        service: ProductService = Depends(_get_service),
    ):
        if not service.submit_for_review(uuid, actor_user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        return {"status": "submitted_for_review", "uuid": uuid}

    @router.post("/{uuid}/approve", response_model=dict)
    async def approve_product(
        uuid: str,
        actor_user_id: str = Query(...),
        comments: Optional[str] = Query(None),
        service: ProductService = Depends(_get_service),
    ):
        if not service.approve(uuid, actor_user_id, comments):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot approve product")
        return {"status": "approved", "uuid": uuid}

    @router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_product(
        uuid: str,
        actor_user_id: str = Query(...),
        service: ProductService = Depends(_get_service),
    ):
        if not service.soft_delete(uuid, actor_user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        return None

    return router


def create_claim_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    """Create a Claim router with the given dependency injection."""
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
            object_uuid=obj.uuid_hex,
            object_type=obj.object_type,
            current_version=obj.current_version,
            lifecycle_state=obj.lifecycle_state,
            owner_user_id=obj.owner_user_id,
            created_at=obj.created_at,
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
                object_uuid=obj.uuid_hex,
                object_type=obj.object_type,
                current_version=obj.current_version,
                lifecycle_state=obj.lifecycle_state,
                owner_user_id=obj.owner_user_id,
                created_at=obj.created_at,
                updated_at=obj.updated_at,
            )
            for obj in objects
        ]

    @router.get("/{uuid}", response_model=dict)
    async def get_claim(
        uuid: str,
        service: ClaimService = Depends(_get_service),
    ):
        data = service.get_with_payload(uuid)
        if data is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
        return data

    @router.post("/{uuid}/link-evidence", response_model=dict)
    async def link_evidence(
        uuid: str,
        evidence_uuid: str = Query(...),
        link_type: str = Query("supports"),
        service: ClaimService = Depends(_get_service),
    ):
        success = service.link_evidence(uuid, evidence_uuid, link_type)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim or evidence not found")
        service.repo.session.commit()
        return {"status": "linked", "claim_uuid": uuid, "evidence_uuid": evidence_uuid}

    @router.get("/{uuid}/evidence-coverage", response_model=dict)
    async def check_evidence_coverage(
        uuid: str,
        service: ClaimService = Depends(_get_service),
    ):
        result = service.check_evidence_coverage(uuid)
        if not result["exists"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
        return result

    @router.post("/{uuid}/submit", response_model=dict)
    async def submit_claim(
        uuid: str,
        actor_user_id: str = Query(...),
        service: ClaimService = Depends(_get_service),
    ):
        if not service.submit_for_review(uuid, actor_user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
        return {"status": "submitted_for_review", "uuid": uuid}

    @router.post("/{uuid}/approve", response_model=dict)
    async def approve_claim(
        uuid: str,
        actor_user_id: str = Query(...),
        comments: Optional[str] = Query(None),
        service: ClaimService = Depends(_get_service),
    ):
        if not service.approve(uuid, actor_user_id, comments):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot approve claim")
        return {"status": "approved", "uuid": uuid}

    @router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_claim(
        uuid: str,
        actor_user_id: str = Query(...),
        service: ClaimService = Depends(_get_service),
    ):
        if not service.soft_delete(uuid, actor_user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
        return None

    return router


def create_evidence_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    """Create an Evidence router with the given dependency injection."""
    router = APIRouter(prefix="/api/v1/evidence", tags=["Evidence"])

    def _get_service(repo: RegulatoryObjectRepository = Depends(get_repo)) -> EvidenceService:
        return EvidenceService(repo)

    @router.post("", response_model=RegulatoryObjectResponse, status_code=status.HTTP_201_CREATED)
    async def create_evidence(
        payload: EvidencePayload,
        owner_user_id: str = Query(...),
        service: EvidenceService = Depends(_get_service),
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
    async def list_evidence(
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        service: EvidenceService = Depends(_get_service),
    ):
        objects = service.list(limit=limit, offset=offset)
        return [
            RegulatoryObjectResponse(
                object_uuid=obj.uuid_hex,
                object_type=obj.object_type,
                current_version=obj.current_version,
                lifecycle_state=obj.lifecycle_state,
                owner_user_id=obj.owner_user_id,
                created_at=obj.created_at,
                updated_at=obj.updated_at,
            )
            for obj in objects
        ]

    @router.get("/{uuid}", response_model=dict)
    async def get_evidence(
        uuid: str,
        service: EvidenceService = Depends(_get_service),
    ):
        data = service.get_with_payload(uuid)
        if data is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
        return data

    @router.post("/{uuid}/submit", response_model=dict)
    async def submit_evidence(
        uuid: str,
        actor_user_id: str = Query(...),
        service: EvidenceService = Depends(_get_service),
    ):
        if not service.submit_for_review(uuid, actor_user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
        return {"status": "submitted_for_review", "uuid": uuid}

    @router.post("/{uuid}/approve", response_model=dict)
    async def approve_evidence(
        uuid: str,
        actor_user_id: str = Query(...),
        comments: Optional[str] = Query(None),
        service: EvidenceService = Depends(_get_service),
    ):
        if not service.approve(uuid, actor_user_id, comments):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot approve evidence")
        return {"status": "approved", "uuid": uuid}

    @router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_evidence(
        uuid: str,
        actor_user_id: str = Query(...),
        service: EvidenceService = Depends(_get_service),
    ):
        if not service.soft_delete(uuid, actor_user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
        return None

    return router
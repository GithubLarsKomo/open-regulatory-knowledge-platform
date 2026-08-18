"""REST API for governed, auditable AI draft records."""

from typing import Callable

from fastapi import APIRouter, Depends, status

from orkp.api.routers import _call_or_404
from orkp.api.schemas import ErrorResponse
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.ai_draft_models import (
    AIDraftCreateRequest,
    AIDraftRegenerateRequest,
    AIDraftResponse,
)
from orkp.domain.ai_draft_service import AIDraftService


def create_ai_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/ai", tags=["AI/RAG"])

    @router.post(
        "/drafts",
        response_model=AIDraftResponse,
        status_code=status.HTTP_201_CREATED,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def create_ai_draft(
        body: AIDraftCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(lambda: AIDraftService(repo).create_draft(body))

    @router.get(
        "/drafts/{draft_uuid}",
        response_model=AIDraftResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_ai_draft(
        draft_uuid: str,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(lambda: AIDraftService(repo).get_draft(draft_uuid))

    @router.post(
        "/drafts/{draft_uuid}/regenerate",
        response_model=AIDraftResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def regenerate_ai_draft(
        draft_uuid: str,
        body: AIDraftRegenerateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: AIDraftService(repo).regenerate_draft(draft_uuid, body)
        )

    return router

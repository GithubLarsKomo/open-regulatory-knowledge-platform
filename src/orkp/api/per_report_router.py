"""REST API for reproducible PER report baselines and draft manifests."""

from typing import Callable

from fastapi import APIRouter, Depends, status

from orkp.api.routers import _call_or_404
from orkp.api.schemas import ErrorResponse
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.per_content_models import (
    PERReportBaselineCreateRequest,
    PERReportBaselineResponse,
)
from orkp.domain.per_draft_models import (
    PERDraftGenerationRequest,
    PERDraftGenerationResponse,
)
from orkp.domain.per_draft_service import PERDraftService
from orkp.domain.per_report_baseline_service import PERReportBaselineService


def create_per_report_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/per-reports", tags=["PER Reports"])

    @router.post(
        "/baselines",
        response_model=PERReportBaselineResponse,
        status_code=status.HTTP_201_CREATED,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def create_per_report_baseline(
        body: PERReportBaselineCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PERReportBaselineService(repo).create_baseline(body)
        )

    @router.post(
        "/{baseline_uuid}/drafts",
        response_model=PERDraftGenerationResponse,
        status_code=status.HTTP_201_CREATED,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def generate_per_draft(
        baseline_uuid: str,
        body: PERDraftGenerationRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PERDraftService(repo).generate_draft(
                baseline_uuid,
                body.generated_by_user_id,
            )
        )

    return router

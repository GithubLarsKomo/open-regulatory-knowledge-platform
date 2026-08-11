"""REST API for reproducible PER report baselines, drafts and documents."""

from typing import Callable

from fastapi import APIRouter, Depends, Response, status

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
from orkp.domain.per_render_models import PERRenderRequest
from orkp.domain.per_render_service import PERRenderService
from orkp.domain.per_report_baseline_service import PERReportBaselineService
from orkp.domain.per_report_object_models import (
    PERReportCanonicalResponse,
    PERReportCreateRequest,
    PERReportLifecycleRequest,
    PERReportRegenerateRequest,
    PERReportResponse,
)
from orkp.domain.per_report_object_service import PERReportObjectService


def create_per_report_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/per-reports", tags=["PER Reports"])

    @router.post(
        "",
        response_model=PERReportResponse,
        status_code=status.HTTP_201_CREATED,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def create_per_report(
        body: PERReportCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(lambda: PERReportObjectService(repo).create_report(body))

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

    @router.get(
        "/{report_uuid}",
        response_model=PERReportResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_per_report(
        report_uuid: str,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(lambda: PERReportObjectService(repo).get_report(report_uuid))

    @router.get(
        "/{report_uuid}/canonical-json",
        response_model=PERReportCanonicalResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_per_report_canonical_json(
        report_uuid: str,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PERReportObjectService(repo).get_canonical_json(report_uuid)
        )

    @router.post(
        "/{report_uuid}/submit",
        response_model=PERReportResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    async def submit_per_report(
        report_uuid: str,
        body: PERReportLifecycleRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PERReportObjectService(repo).submit_for_review(
                report_uuid,
                body.actor_user_id,
            )
        )

    @router.post(
        "/{report_uuid}/approve",
        response_model=PERReportResponse,
        responses={
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    async def approve_per_report(
        report_uuid: str,
        body: PERReportLifecycleRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PERReportObjectService(repo).approve(
                report_uuid,
                body.actor_user_id,
                body.comments,
            )
        )

    @router.post(
        "/{report_uuid}/regenerate",
        response_model=PERReportResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def regenerate_per_report(
        report_uuid: str,
        body: PERReportRegenerateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PERReportObjectService(repo).regenerate_report(report_uuid, body)
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

    @router.post(
        "/{baseline_uuid}/renders/{render_format}",
        status_code=status.HTTP_201_CREATED,
        response_class=Response,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def render_per_document(
        baseline_uuid: str,
        render_format: str,
        body: PERRenderRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        result = _call_or_404(
            lambda: PERRenderService(repo).render(
                baseline_uuid,
                render_format,
                body.generated_by_user_id,
            )
        )
        return Response(
            content=result.content,
            media_type=result.media_type,
            status_code=status.HTTP_201_CREATED,
            headers={
                "Content-Disposition": f'attachment; filename="{result.filename}"',
                "X-Artifact-UUID": result.artifact_uuid,
                "X-Baseline-UUID": result.baseline_uuid,
                "X-Checksum-SHA256": result.checksum_sha256,
            },
        )

    return router

"""REST API for the Performance domain."""

from typing import Callable

from fastapi import APIRouter, Depends, status

from orkp.api.routers import _call_or_404
from orkp.api.schemas import ErrorResponse
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.performance_models import (
    PerformanceStudyCreateRequest,
    PerformanceStudyResponse,
)
from orkp.domain.performance_result_models import (
    PerformanceResultCreateRequest,
    PerformanceResultResponse,
)
from orkp.domain.performance_result_service import PerformanceResultService
from orkp.domain.performance_service import PerformanceStudyService


def create_performance_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(tags=["Performance"])

    @router.post(
        "/api/v1/products/{product_uuid}/performance-studies",
        response_model=PerformanceStudyResponse,
        status_code=status.HTTP_201_CREATED,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def create_performance_study(
        product_uuid: str,
        body: PerformanceStudyCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PerformanceStudyService(repo).create_study(product_uuid, body)
        )

    @router.get(
        "/api/v1/performance-studies/{study_uuid}/versions/{version}",
        response_model=PerformanceStudyResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_performance_study(
        study_uuid: str,
        version: int,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PerformanceStudyService(repo).get_study(study_uuid, version)
        )

    @router.post(
        "/api/v1/performance-studies/{study_uuid}/results",
        response_model=PerformanceResultResponse,
        status_code=status.HTTP_201_CREATED,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def create_performance_result(
        study_uuid: str,
        body: PerformanceResultCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PerformanceResultService(repo).create_result(study_uuid, body)
        )

    @router.get(
        "/api/v1/performance-results/{result_uuid}/versions/{version}",
        response_model=PerformanceResultResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_performance_result(
        result_uuid: str,
        version: int,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PerformanceResultService(repo).get_result(result_uuid, version)
        )

    return router

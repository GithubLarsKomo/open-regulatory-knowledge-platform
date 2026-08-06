"""REST API for reproducible Risk Management Report baselines."""

from typing import Callable

from fastapi import APIRouter, Depends, status

from orkp.api.routers import _call_or_404
from orkp.api.schemas import ErrorResponse
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.risk_report_models import (
    RiskReportBaselineCreateRequest,
    RiskReportBaselineResponse,
    RiskReportGenerationRequest,
    RiskReportGenerationResponse,
)
from orkp.domain.risk_report_service import RiskReportService


def create_risk_report_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/risk-report-baselines", tags=["Risk Reports"])

    @router.post(
        "",
        response_model=RiskReportBaselineResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def create_risk_report_baseline(
        body: RiskReportBaselineCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(lambda: RiskReportService(repo).create_baseline(body))

    @router.get(
        "/{baseline_uuid}",
        response_model=RiskReportBaselineResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_risk_report_baseline(
        baseline_uuid: str,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: RiskReportService(repo).get_baseline(baseline_uuid)
        )

    @router.post(
        "/{baseline_uuid}/reports",
        response_model=RiskReportGenerationResponse,
        status_code=status.HTTP_201_CREATED,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def generate_risk_report(
        baseline_uuid: str,
        body: RiskReportGenerationRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: RiskReportService(repo).generate_report(
                baseline_uuid,
                body.generated_by_user_id,
            )
        )

    return router

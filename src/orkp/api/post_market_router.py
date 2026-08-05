"""Post-market safety information and Risk Impact Assessment API."""

from typing import Callable

from fastapi import APIRouter, Depends, Query, status

from orkp.api.routers import _call_or_404
from orkp.api.schemas import ErrorResponse
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.post_market_models import (
    PostMarketInformationCreateRequest,
    PostMarketInformationResponse,
    PostMarketIngestionResponse,
    RiskImpactAssessmentCompleteRequest,
    RiskImpactAssessmentResponse,
)
from orkp.domain.post_market_service import PostMarketRiskService


def create_post_market_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    """Create endpoints for REQ-RISK-0019/0020 workflows."""
    router = APIRouter(tags=["Post-Market Risk"])

    @router.post(
        "/api/v1/risk-analyses/{risk_analysis_uuid}/post-market-information",
        response_model=PostMarketIngestionResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def ingest_post_market_information(
        risk_analysis_uuid: str,
        body: PostMarketInformationCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PostMarketRiskService(repo).ingest_information(
                risk_analysis_uuid,
                body,
            )
        )

    @router.get(
        "/api/v1/post-market-information/{information_uuid}/versions/{version}",
        response_model=PostMarketInformationResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_post_market_information(
        information_uuid: str,
        version: int,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PostMarketRiskService(repo).get_information(
                information_uuid,
                version,
            )
        )

    @router.get(
        "/api/v1/risk-impact-assessments/{assessment_uuid}/versions/{version}",
        response_model=RiskImpactAssessmentResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_risk_impact_assessment(
        assessment_uuid: str,
        version: int,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PostMarketRiskService(repo).get_assessment(
                assessment_uuid,
                version,
            )
        )

    @router.post(
        "/api/v1/risk-impact-assessments/{assessment_uuid}/complete",
        response_model=RiskImpactAssessmentResponse,
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def complete_risk_impact_assessment(
        assessment_uuid: str,
        body: RiskImpactAssessmentCompleteRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PostMarketRiskService(repo).complete_assessment(
                assessment_uuid,
                body,
            )
        )

    @router.post(
        "/api/v1/risk-impact-assessments/{assessment_uuid}/transitions/{new_state}",
        response_model=RiskImpactAssessmentResponse,
        responses={
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def transition_risk_impact_assessment(
        assessment_uuid: str,
        new_state: str,
        actor_user_id: str = Query(..., min_length=1),
        comments: str | None = Query(None),
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: PostMarketRiskService(repo).transition_assessment(
                assessment_uuid,
                new_state,
                actor_user_id,
                comments,
            )
        )

    return router

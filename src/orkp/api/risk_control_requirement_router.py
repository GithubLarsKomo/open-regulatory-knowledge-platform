"""REST API for Risk Control to Requirement traceability."""

from typing import Callable

from fastapi import APIRouter, Depends, Query, status

from orkp.api.routers import _call_or_404
from orkp.api.schemas import ErrorResponse
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.risk_control_requirement_service import (
    RiskControlRequirementLinkResponse,
    RiskControlRequirementService,
)


def create_risk_control_requirement_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(tags=["Risk Control Requirements"])

    @router.post(
        "/api/v1/risk-controls/{risk_control_uuid}/requirements/{requirement_uuid}",
        response_model=RiskControlRequirementLinkResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def link_risk_control_requirement(
        risk_control_uuid: str,
        requirement_uuid: str,
        actor_user_id: str = Query(..., min_length=1),
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: RiskControlRequirementService(repo).link_requirement(
                risk_control_uuid,
                requirement_uuid,
                actor_user_id,
            )
        )

    return router

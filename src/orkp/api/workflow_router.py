"""REST API for auditable workflow approval history."""

from typing import Callable

from fastapi import APIRouter, Depends

from orkp.api.schemas import ErrorResponse
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.workflow_models import ApprovalDecisionResponse
from orkp.domain.workflow_service import WorkflowService


def create_workflow_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Workflow"])

    @router.get(
        "/objects/{object_uuid}/approvals",
        response_model=list[ApprovalDecisionResponse],
        responses={404: {"model": ErrorResponse}},
        summary="Get approval/rejection history for an object",
    )
    async def list_approval_history(
        object_uuid: str,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return WorkflowService(repo).list_approval_history(object_uuid)

    return router

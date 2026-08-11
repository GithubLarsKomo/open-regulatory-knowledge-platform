"""Read-only REST API for version-aware regulatory traceability graph queries."""

from typing import Callable

from fastapi import APIRouter, Depends, Query

from orkp.api.routers import _call_or_404
from orkp.api.schemas import ErrorResponse
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.graph_models import TraceabilityGraph
from orkp.domain.graph_service import GraphProjectionService


def create_graph_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/graph", tags=["Knowledge Graph"])

    @router.get(
        "/objects/{object_uuid}/versions/{object_version}/traceability",
        response_model=TraceabilityGraph,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_traceability_graph(
        object_uuid: str,
        object_version: int,
        depth: int = Query(1, ge=0, le=10),
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: GraphProjectionService(repo).traceability(
                object_uuid,
                object_version,
                depth,
            )
        )

    return router

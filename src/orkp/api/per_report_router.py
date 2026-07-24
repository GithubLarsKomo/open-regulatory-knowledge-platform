"""FastAPI router for baseline-pinned PER report generation."""

import json
from typing import Callable

from fastapi import APIRouter, Depends, Response, status

from orkp.api.routers import _call_or_404
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.per_report_models import PERReportCreateRequest, PERReportResponse
from orkp.domain.per_report_service import PERReportService


def create_per_report_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(tags=["PER Reports"])

    @router.post(
        "/api/v1/products/{product_uuid}/per-reports",
        response_model=PERReportResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_per_report(
        product_uuid: str,
        body: PERReportCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        service = PERReportService(repo)
        return _call_or_404(
            lambda: service.generate(
                product_uuid=product_uuid,
                baseline_uuid=body.baseline_uuid,
                report_type=body.report_type,
                generated_by=body.generated_by,
            )
        )

    @router.get(
        "/api/v1/per-reports/{report_uuid}",
        response_model=PERReportResponse,
    )
    async def get_per_report(
        report_uuid: str,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(lambda: PERReportService(repo).get(report_uuid))

    @router.get("/api/v1/per-reports/{report_uuid}/canonical-json")
    async def get_per_report_canonical_json(
        report_uuid: str,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        canonical = _call_or_404(
            lambda: PERReportService(repo).canonical_json(report_uuid)
        )
        # Re-encode only to guarantee that the response body exactly matches the
        # canonical serialization produced by the domain service.
        json.loads(canonical)
        return Response(content=canonical, media_type="application/json")

    return router

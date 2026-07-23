"""
Risk Evaluation API router for ORKP.

Provides typed endpoints for creating and reading Initial and Residual Risk Evaluations.
"""

from typing import Callable

from fastapi import APIRouter, Depends, status

from orkp.api.schemas import ErrorResponse
from orkp.api.routers import _call_or_404
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.risk_models import (
    InitialRiskEvaluationCreateRequest,
    InitialRiskEvaluationResponse,
    ResidualRiskEvaluationCreateRequest,
    ResidualRiskEvaluationResponse,
)
from orkp.domain.initial_risk_evaluation_service import InitialRiskEvaluationService
from orkp.domain.residual_risk_evaluation_service import ResidualRiskEvaluationService
from orkp.domain.exceptions import InvalidPersistedPayloadError
from orkp.domain.versioned_loader import load_versioned_object


def create_risk_evaluation_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(tags=["Risk Evaluations"])

    # ------------------------------------------------------------------
    # POST /risk-analyses/{risk_analysis_uuid}/initial-evaluations
    # ------------------------------------------------------------------
    @router.post(
        "/api/v1/risk-analyses/{risk_analysis_uuid}/initial-evaluations",
        response_model=InitialRiskEvaluationResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    async def create_initial_evaluation(
        risk_analysis_uuid: str,
        body: InitialRiskEvaluationCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        service = InitialRiskEvaluationService(repo)
        return _call_or_404(lambda: service.create_evaluation(risk_analysis_uuid, body))

    # ------------------------------------------------------------------
    # POST /risk-analyses/{risk_analysis_uuid}/residual-evaluations
    # ------------------------------------------------------------------
    @router.post(
        "/api/v1/risk-analyses/{risk_analysis_uuid}/residual-evaluations",
        response_model=ResidualRiskEvaluationResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    async def create_residual_evaluation(
        risk_analysis_uuid: str,
        body: ResidualRiskEvaluationCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        service = ResidualRiskEvaluationService(repo)
        return _call_or_404(lambda: service.create_evaluation(risk_analysis_uuid, body))

    # ------------------------------------------------------------------
    # GET /initial-risk-evaluations/{evaluation_uuid}/versions/{version}
    # ------------------------------------------------------------------
    @router.get(
        "/api/v1/initial-risk-evaluations/{evaluation_uuid}/versions/{version}",
        response_model=InitialRiskEvaluationResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_initial_evaluation(
        evaluation_uuid: str,
        version: int,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: _get_typed_evaluation(
                repo,
                evaluation_uuid,
                version,
                "initial_risk_evaluation",
                InitialRiskEvaluationResponse,
            )
        )

    # ------------------------------------------------------------------
    # GET /residual-risk-evaluations/{evaluation_uuid}/versions/{version}
    # ------------------------------------------------------------------
    @router.get(
        "/api/v1/residual-risk-evaluations/{evaluation_uuid}/versions/{version}",
        response_model=ResidualRiskEvaluationResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_residual_evaluation(
        evaluation_uuid: str,
        version: int,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: _get_typed_evaluation(
                repo,
                evaluation_uuid,
                version,
                "residual_risk_evaluation",
                ResidualRiskEvaluationResponse,
            )
        )

    return router


def _get_typed_evaluation(repo, uuid_hex, version, expected_type, response_cls):
    """Load and return a typed evaluation by UUID + version."""
    from orkp.domain.risk_models import (
        InitialRiskEvaluationPayload,
        ResidualRiskEvaluationPayload,
    )

    payload_cls = (
        InitialRiskEvaluationPayload
        if expected_type == "initial_risk_evaluation"
        else ResidualRiskEvaluationPayload
    )
    loaded = load_versioned_object(repo, uuid_hex, version, expected_type)
    from pydantic import ValidationError

    try:
        validated_payload = payload_cls(**loaded.payload)
    except ValidationError as exc:
        raise InvalidPersistedPayloadError(
            f"Stored {expected_type} payload invalid"
        ) from exc
    return response_cls(
        object_uuid=loaded.object.uuid_hex,
        object_version=version,
        lifecycle_state=loaded.object.lifecycle_state,
        payload=validated_payload,
    )

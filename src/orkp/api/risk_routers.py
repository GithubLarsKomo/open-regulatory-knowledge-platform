"""Risk Evaluation, Control Verification and Benefit-Risk API router for ORKP."""

from typing import Callable

from fastapi import APIRouter, Depends, Query, status
from pydantic import ValidationError

from orkp.api.routers import _call_or_404
from orkp.api.schemas import ErrorResponse
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.benefit_risk_models import (
    BenefitRiskAnalysisCreateRequest,
    BenefitRiskAnalysisResponse,
)
from orkp.domain.benefit_risk_service import BenefitRiskAnalysisService
from orkp.domain.control_verification_queries import (
    list_control_verifications_for_risk_analysis,
)
from orkp.domain.control_verification_service import ControlVerificationService
from orkp.domain.exceptions import InvalidPersistedPayloadError
from orkp.domain.initial_risk_evaluation_service import InitialRiskEvaluationService
from orkp.domain.residual_risk_evaluation_service import ResidualRiskEvaluationService
from orkp.domain.risk_models import (
    ControlVerificationCreateRequest,
    ControlVerificationResponse,
    InitialRiskEvaluationCreateRequest,
    InitialRiskEvaluationPayload,
    InitialRiskEvaluationResponse,
    ResidualRiskEvaluationCreateRequest,
    ResidualRiskEvaluationPayload,
    ResidualRiskEvaluationResponse,
)
from orkp.domain.versioned_loader import load_versioned_object


def create_risk_evaluation_router(
    get_repo: Callable[[], RegulatoryObjectRepository],
) -> APIRouter:
    router = APIRouter(tags=["Risk Evaluations"])

    @router.post(
        "/api/v1/risk-analyses/{risk_analysis_uuid}/initial-evaluations",
        response_model=InitialRiskEvaluationResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def create_initial_evaluation(
        risk_analysis_uuid: str,
        body: InitialRiskEvaluationCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: InitialRiskEvaluationService(repo).create_evaluation(
                risk_analysis_uuid, body
            )
        )

    @router.post(
        "/api/v1/risk-analyses/{risk_analysis_uuid}/residual-evaluations",
        response_model=ResidualRiskEvaluationResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def create_residual_evaluation(
        risk_analysis_uuid: str,
        body: ResidualRiskEvaluationCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: ResidualRiskEvaluationService(repo).create_evaluation(
                risk_analysis_uuid, body
            )
        )

    @router.post(
        "/api/v1/residual-risk-evaluations/{evaluation_uuid}/benefit-risk-analyses",
        response_model=BenefitRiskAnalysisResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def create_benefit_risk_analysis(
        evaluation_uuid: str,
        body: BenefitRiskAnalysisCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: BenefitRiskAnalysisService(repo).create_analysis(
                evaluation_uuid, body
            )
        )

    @router.post(
        "/api/v1/benefit-risk-analyses/{analysis_uuid}/transitions/{new_state}",
        response_model=BenefitRiskAnalysisResponse,
        responses={
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def transition_benefit_risk_analysis(
        analysis_uuid: str,
        new_state: str,
        actor_user_id: str = Query(..., min_length=1),
        comments: str | None = Query(None),
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: BenefitRiskAnalysisService(repo).transition_state(
                analysis_uuid,
                new_state,
                actor_user_id,
                comments,
            )
        )

    @router.get(
        "/api/v1/benefit-risk-analyses/{analysis_uuid}/versions/{version}",
        response_model=BenefitRiskAnalysisResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_benefit_risk_analysis(
        analysis_uuid: str,
        version: int,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: BenefitRiskAnalysisService(repo).get_analysis(
                analysis_uuid, version
            )
        )

    @router.post(
        "/api/v1/risk-controls/{risk_control_uuid}/verifications",
        response_model=ControlVerificationResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def create_control_verification(
        risk_control_uuid: str,
        body: ControlVerificationCreateRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: ControlVerificationService(repo).create_verification(
                risk_control_uuid, body
            )
        )

    @router.post(
        "/api/v1/control-verifications/{verification_uuid}/transitions/{new_state}",
        response_model=ControlVerificationResponse,
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def transition_control_verification(
        verification_uuid: str,
        new_state: str,
        actor_user_id: str = Query(..., min_length=1),
        comments: str | None = Query(None),
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: ControlVerificationService(repo).transition_state(
                verification_uuid,
                new_state,
                actor_user_id,
                comments,
            )
        )

    @router.get(
        "/api/v1/control-verifications/{verification_uuid}/versions/{version}",
        response_model=ControlVerificationResponse,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def get_control_verification(
        verification_uuid: str,
        version: int,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: ControlVerificationService(repo).get_verification(
                verification_uuid, version
            )
        )

    @router.get(
        "/api/v1/risk-controls/{risk_control_uuid}/verifications",
        response_model=list[ControlVerificationResponse],
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def list_control_verifications(
        risk_control_uuid: str,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: ControlVerificationService(repo).list_for_risk_control(
                risk_control_uuid
            )
        )

    @router.get(
        "/api/v1/risk-analyses/{risk_analysis_uuid}/control-verifications",
        response_model=list[ControlVerificationResponse],
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def list_risk_analysis_control_verifications(
        risk_analysis_uuid: str,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        return _call_or_404(
            lambda: list_control_verifications_for_risk_analysis(
                repo, risk_analysis_uuid
            )
        )

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
                InitialRiskEvaluationPayload,
                InitialRiskEvaluationResponse,
            )
        )

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
                ResidualRiskEvaluationPayload,
                ResidualRiskEvaluationResponse,
            )
        )

    return router


def _get_typed_evaluation(
    repo,
    uuid_hex,
    version,
    expected_type,
    payload_cls,
    response_cls,
):
    loaded = load_versioned_object(repo, uuid_hex, version, expected_type)
    try:
        payload = payload_cls(**loaded.payload)
    except ValidationError as exc:
        raise InvalidPersistedPayloadError(
            f"Stored {expected_type} payload invalid"
        ) from exc
    return response_cls(
        object_uuid=loaded.object.uuid_hex,
        object_version=version,
        lifecycle_state=loaded.object.lifecycle_state,
        payload=payload,
    )

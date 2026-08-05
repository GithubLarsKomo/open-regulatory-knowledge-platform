"""Version-pinned Benefit-Risk Analysis service."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.benefit_risk_models import (
    BenefitRiskAnalysisCreateRequest,
    BenefitRiskAnalysisPayload,
    BenefitRiskAnalysisResponse,
)
from orkp.domain.exceptions import (
    InvalidObjectIdentifierError,
    InvalidPersistedPayloadError,
    InvalidRelationError,
    ObjectNotFoundError,
    RiskEvaluationError,
    SelfApprovalNotAllowedError,
)
from orkp.domain.risk_models import ResidualRiskEvaluationPayload
from orkp.domain.versioned_loader import load_risk_policy, load_versioned_object


class BenefitRiskAnalysisService:
    """Create, transition and read Benefit-Risk Analyses."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_analysis(
        self,
        residual_evaluation_hex: str,
        request: BenefitRiskAnalysisCreateRequest,
    ) -> BenefitRiskAnalysisResponse:
        residual = load_versioned_object(
            self.repo,
            residual_evaluation_hex,
            request.residual_evaluation.object_version,
            "residual_risk_evaluation",
        )
        if residual.object.uuid_hex != request.residual_evaluation.object_uuid:
            raise InvalidRelationError(
                "Path residual-risk UUID does not match request reference"
            )
        if (
            residual.object.current_version
            != request.residual_evaluation.object_version
        ):
            raise InvalidRelationError(
                "Benefit-Risk Analysis must reference the current residual-risk version"
            )

        try:
            residual_payload = ResidualRiskEvaluationPayload(**residual.payload)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Stored residual risk evaluation payload is invalid"
            ) from exc

        if residual_payload.acceptable or not residual_payload.benefit_risk_required:
            raise RiskEvaluationError(
                "Benefit-Risk Analysis requires an unacceptable residual risk "
                "that is policy-gated for benefit-risk analysis"
            )

        expected_risk = (
            residual_payload.risk_analysis_uuid,
            residual_payload.risk_analysis_version,
        )
        requested_risk = (
            request.risk_analysis.object_uuid,
            request.risk_analysis.object_version,
        )
        if requested_risk != expected_risk:
            raise InvalidRelationError(
                "Benefit-Risk Analysis references a different risk-analysis context"
            )

        expected_policy = (
            residual_payload.risk_policy_uuid,
            residual_payload.risk_policy_version,
        )
        requested_policy = (
            request.risk_policy.object_uuid,
            request.risk_policy.object_version,
        )
        if requested_policy != expected_policy:
            raise InvalidRelationError(
                "Benefit-Risk Analysis references a different risk-policy context"
            )

        risk_analysis = load_versioned_object(
            self.repo,
            request.risk_analysis.object_uuid,
            request.risk_analysis.object_version,
            "risk_analysis",
        )
        if risk_analysis.object.current_version != request.risk_analysis.object_version:
            raise InvalidRelationError(
                "Benefit-Risk Analysis must reference the current risk-analysis version"
            )
        risk_policy = load_risk_policy(
            self.repo,
            request.risk_policy.object_uuid,
            request.risk_policy.object_version,
        )

        relations = self.repo.list_active_relations_for_source(
            residual.object.object_uuid
        )
        has_risk_relation = any(
            relation.relation_type == "residual_of"
            and relation.source_version == request.residual_evaluation.object_version
            and relation.target_uuid == risk_analysis.object.object_uuid
            and relation.target_version == request.risk_analysis.object_version
            for relation in relations
        )
        if not has_risk_relation:
            raise InvalidRelationError(
                "Residual risk evaluation lacks the expected version-pinned "
                "risk-analysis relation"
            )

        has_policy_relation = any(
            relation.relation_type == "uses_risk_policy"
            and relation.source_version == request.residual_evaluation.object_version
            and relation.target_uuid == risk_policy.object.object_uuid
            and relation.target_version == request.risk_policy.object_version
            for relation in relations
        )
        if not has_policy_relation:
            raise InvalidRelationError(
                "Residual risk evaluation lacks the expected version-pinned "
                "risk-policy relation"
            )

        payload = BenefitRiskAnalysisPayload(
            **request.model_dump(),
            analysis_id=f"bra-{uuid4().hex[:12]}",
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            analysis, _ = self.repo.create_object(
                object_type="benefit_risk",
                payload=payload.model_dump(),
                owner_user_id=request.evaluator_user_id,
                created_by=request.evaluator_user_id,
            )
            version = analysis.current_version
            self.repo.create_relation(
                source_uuid=analysis.object_uuid,
                source_version=version,
                target_uuid=residual.object.object_uuid,
                target_version=request.residual_evaluation.object_version,
                relation_type="benefit_risk_for",
                created_by=request.evaluator_user_id,
            )
            self.repo.create_relation(
                source_uuid=analysis.object_uuid,
                source_version=version,
                target_uuid=risk_policy.object.object_uuid,
                target_version=request.risk_policy.object_version,
                relation_type="uses_risk_policy",
                created_by=request.evaluator_user_id,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return BenefitRiskAnalysisResponse(
            object_uuid=analysis.uuid_hex,
            object_version=version,
            lifecycle_state=analysis.lifecycle_state,
            payload=payload,
        )

    def transition_state(
        self,
        analysis_hex: str,
        new_state: str,
        actor_user_id: str,
        comments: str | None = None,
    ) -> BenefitRiskAnalysisResponse:
        loaded = load_versioned_object(
            self.repo,
            analysis_hex,
            self._current_version(analysis_hex),
            "benefit_risk",
        )
        if new_state == "approved" and actor_user_id == loaded.object.owner_user_id:
            raise SelfApprovalNotAllowedError(
                "Benefit-Risk Analysis must be approved by another user"
            )
        try:
            self.repo.transition_state(
                loaded.object.object_uuid,
                new_state,
                actor_user_id,
                comments=comments,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise
        return self.get_analysis(loaded.object.uuid_hex, loaded.object.current_version)

    def get_analysis(
        self,
        analysis_hex: str,
        version: int,
    ) -> BenefitRiskAnalysisResponse:
        loaded = load_versioned_object(
            self.repo,
            analysis_hex,
            version,
            "benefit_risk",
        )
        try:
            payload = BenefitRiskAnalysisPayload(**loaded.payload)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Stored Benefit-Risk Analysis payload is invalid"
            ) from exc
        return BenefitRiskAnalysisResponse(
            object_uuid=loaded.object.uuid_hex,
            object_version=version,
            lifecycle_state=loaded.object.lifecycle_state,
            payload=payload,
        )

    def _current_version(self, analysis_hex: str) -> int:
        try:
            normalized = UUID(analysis_hex).hex
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidObjectIdentifierError(
                f"Invalid UUID format: {analysis_hex}"
            ) from exc
        obj = self.repo.get_by_uuid_hex(normalized)
        if obj is None:
            raise ObjectNotFoundError(f"Benefit-Risk Analysis {normalized} not found")
        return obj.current_version

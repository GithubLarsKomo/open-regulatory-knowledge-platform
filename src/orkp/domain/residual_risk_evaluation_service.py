"""Residual Risk Evaluation service for ORKP."""

from datetime import datetime, timezone
import uuid

from pydantic import ValidationError

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.control_verification_service import ControlVerificationService
from orkp.domain.exceptions import InvalidRelationError, InvalidPersistedPayloadError
from orkp.domain.risk_models import (
    InitialRiskEvaluationPayload,
    ResidualRiskEvaluationCreateRequest,
    ResidualRiskEvaluationPayload,
    ResidualRiskEvaluationResponse,
)
from orkp.domain.risk_evaluation import compare_initial_and_residual_risk
from orkp.domain.versioned_loader import load_versioned_object, load_risk_policy


class ResidualRiskEvaluationService:
    """Create version-pinned residual risk evaluations atomically."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_evaluation(
        self,
        risk_analysis_hex: str,
        request: ResidualRiskEvaluationCreateRequest,
    ) -> ResidualRiskEvaluationResponse:
        risk_analysis_hex = uuid.UUID(risk_analysis_hex).hex
        risk_analysis = load_versioned_object(
            self.repo,
            risk_analysis_hex,
            request.risk_analysis_version,
            "risk_analysis",
        )
        initial_evaluation = load_versioned_object(
            self.repo,
            request.initial_evaluation_uuid,
            request.initial_evaluation_version,
            "initial_risk_evaluation",
        )

        try:
            initial_payload = InitialRiskEvaluationPayload(**initial_evaluation.payload)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                f"Initial evaluation {request.initial_evaluation_uuid} payload invalid"
            ) from exc

        if initial_payload.risk_analysis_uuid != risk_analysis_hex:
            raise InvalidRelationError(
                "Initial evaluation does not belong to this risk analysis"
            )
        if initial_payload.risk_analysis_version != request.risk_analysis_version:
            raise InvalidRelationError(
                "Initial evaluation references a different risk-analysis version"
            )

        policy_loaded = load_risk_policy(
            self.repo,
            initial_payload.risk_policy_uuid,
            initial_payload.risk_policy_version,
        )
        policy = policy_loaded.policy

        verification_service = ControlVerificationService(self.repo)
        verification_responses = []
        seen_controls: set[tuple[str, int]] = set()
        for reference in request.control_verifications:
            verification = verification_service.assert_eligible_for_residual(
                reference.object_uuid,
                reference.object_version,
                risk_analysis_hex,
                request.risk_analysis_version,
                request.initial_evaluation_uuid,
                request.initial_evaluation_version,
                initial_payload.risk_policy_uuid,
                initial_payload.risk_policy_version,
            )
            control_key = (
                verification.payload.risk_control.object_uuid,
                verification.payload.risk_control.object_version,
            )
            if control_key in seen_controls:
                raise InvalidRelationError(
                    "Multiple control verifications reference the same risk-control version"
                )
            seen_controls.add(control_key)
            verification_responses.append(verification)

        if request.residual_severity not in policy.severity_scale:
            raise InvalidRelationError(
                f"Severity '{request.residual_severity}' not in policy scale"
            )
        if request.residual_probability not in policy.probability_scale:
            raise InvalidRelationError(
                f"Probability '{request.residual_probability}' not in policy scale"
            )

        comparison = compare_initial_and_residual_risk(
            initial_payload.severity,
            initial_payload.probability,
            request.residual_severity,
            request.residual_probability,
            policy,
        )
        residual_level = comparison["residual_risk"]["risk_level"]
        action_required = policy.get_required_action(residual_level)
        benefit_risk_required = (
            policy.is_benefit_risk_required(residual_level)
            and not comparison["acceptable"]
        )

        payload_dict = {
            "evaluation_id": f"rre-{uuid.uuid4().hex[:12]}",
            "risk_analysis_uuid": risk_analysis_hex,
            "risk_analysis_version": request.risk_analysis_version,
            "initial_evaluation_uuid": request.initial_evaluation_uuid,
            "initial_evaluation_version": request.initial_evaluation_version,
            "control_verifications": [
                reference.model_dump() for reference in request.control_verifications
            ],
            "residual_severity": request.residual_severity,
            "residual_probability": request.residual_probability,
            "calculated_risk_level": residual_level,
            "acceptable": comparison["acceptable"],
            "action_required": action_required,
            "severity_improved": comparison["severity_improved"],
            "probability_improved": comparison["probability_improved"],
            "severity_worsened": comparison["severity_worsened"],
            "probability_worsened": comparison["probability_worsened"],
            "risk_level_improved": comparison["risk_level_improved"],
            "reduced": comparison["reduced"],
            "regression_detected": comparison["regression_detected"],
            "benefit_risk_required": benefit_risk_required,
            "risk_policy_uuid": initial_payload.risk_policy_uuid,
            "risk_policy_version": initial_payload.risk_policy_version,
            "policy_revision": policy.version,
            "evaluator_user_id": request.evaluator_user_id,
            "rationale": request.rationale,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            payload = ResidualRiskEvaluationPayload(**payload_dict)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Invalid residual evaluation payload"
            ) from exc

        try:
            evaluation, _ = self.repo.create_object(
                object_type="residual_risk_evaluation",
                payload=payload.model_dump(),
                owner_user_id=request.evaluator_user_id,
                created_by=request.evaluator_user_id,
            )
            version = evaluation.current_version
            self.repo.create_relation(
                source_uuid=evaluation.object_uuid,
                source_version=version,
                target_uuid=risk_analysis.object.object_uuid,
                target_version=request.risk_analysis_version,
                relation_type="residual_of",
                created_by=request.evaluator_user_id,
            )
            self.repo.create_relation(
                source_uuid=evaluation.object_uuid,
                source_version=version,
                target_uuid=initial_evaluation.object.object_uuid,
                target_version=request.initial_evaluation_version,
                relation_type="derived_from_initial_evaluation",
                created_by=request.evaluator_user_id,
            )
            self.repo.create_relation(
                source_uuid=evaluation.object_uuid,
                source_version=version,
                target_uuid=policy_loaded.object.object_uuid,
                target_version=initial_payload.risk_policy_version,
                relation_type="uses_risk_policy",
                created_by=request.evaluator_user_id,
            )
            for verification in verification_responses:
                verification_obj = self.repo.get_by_uuid_hex(verification.object_uuid)
                self.repo.create_relation(
                    source_uuid=evaluation.object_uuid,
                    source_version=version,
                    target_uuid=verification_obj.object_uuid,
                    target_version=verification.object_version,
                    relation_type="derived_from",
                    created_by=request.evaluator_user_id,
                    properties={"role": "based_on_control_verification"},
                )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return ResidualRiskEvaluationResponse(
            object_uuid=evaluation.uuid_hex,
            object_version=version,
            lifecycle_state=evaluation.lifecycle_state,
            payload=payload,
        )

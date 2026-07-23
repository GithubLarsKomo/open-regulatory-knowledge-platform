"""
Residual Risk Evaluation service for ORKP.

Persists the residual risk evaluation referencing exact InitialEvaluation
and RiskPolicy versions. Uses one atomic transaction.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    InvalidRelationError,
    InvalidPersistedPayloadError,
    ObjectTypeMismatchError,
    ObjectVersionNotFoundError,
)
from orkp.domain.risk_models import (
    ResidualRiskEvaluationCreateRequest,
    ResidualRiskEvaluationPayload,
    InitialRiskEvaluationPayload,
    REQUIRED_ACTIONS,
)
from orkp.domain.risk_evaluation import compare_initial_and_residual_risk
from orkp.domain.versioned_loader import load_versioned_object, load_risk_policy


class ResidualRiskEvaluationService:
    """Service for creating persisted Residual Risk Evaluations."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_evaluation(
        self,
        risk_analysis_hex: str,
        request: ResidualRiskEvaluationCreateRequest,
    ) -> Dict[str, Any]:
        """Create a persisted Residual Risk Evaluation.

        Pins exact RiskAnalysis, InitialEvaluation, and RiskPolicy versions.
        Client must not supply derived fields.
        Uses one atomic transaction.
        """
        # 1. Load RiskAnalysis with exact version and type check
        ra_obj, _ = load_versioned_object(
            self.repo, risk_analysis_hex, request.risk_analysis_version,
            'risk_analysis',
        )

        # 2. Load and validate InitialEvaluation
        ie_obj, ie_payload = load_versioned_object(
            self.repo, request.initial_evaluation_uuid, request.initial_evaluation_version,
            'initial_risk_evaluation',
        )

        # 3. Validate InitialEvaluation payload with Pydantic
        try:
            validated_ie = InitialRiskEvaluationPayload(**ie_payload)
        except Exception as e:
            raise InvalidPersistedPayloadError(
                f"Initial evaluation {request.initial_evaluation_uuid} payload invalid: {e}"
            )

        # 4. Verify initial evaluation belongs to this risk analysis
        if validated_ie.risk_analysis_uuid != risk_analysis_hex:
            raise InvalidRelationError(
                "Initial evaluation does not belong to this risk analysis"
            )

        if validated_ie.risk_analysis_version != request.risk_analysis_version:
            raise InvalidRelationError(
                f"Initial evaluation references risk analysis version {validated_ie.risk_analysis_version}, "
                f"but request specifies version {request.risk_analysis_version}"
            )

        # 5. Load the exact RiskPolicy version from the initial evaluation
        policy_obj, policy_payload, policy = load_risk_policy(
            self.repo, validated_ie.risk_policy_uuid, validated_ie.risk_policy_version,
        )

        # 6. Validate residual severity and probability against policy
        if request.residual_severity not in policy.severity_scale:
            raise InvalidRelationError(
                f"Severity '{request.residual_severity}' not in policy scale: {policy.severity_scale}"
            )
        if request.residual_probability not in policy.probability_scale:
            raise InvalidRelationError(
                f"Probability '{request.residual_probability}' not in policy scale: {policy.probability_scale}"
            )

        # 7. Calculate comparison using initial evaluation data (not defaults)
        comparison = compare_initial_and_residual_risk(
            validated_ie.severity, validated_ie.probability,
            request.residual_severity, request.residual_probability,
            policy,
        )

        # 8. Determine action_required from policy
        residual_level = comparison['residual_risk']['risk_level']
        action_required = policy.get_required_action(residual_level)

        # 9. Determine benefit_risk_required from policy rules
        benefit_risk_required = policy.is_benefit_risk_required(residual_level) and not comparison['acceptable']

        # 10. Build and validate payload
        import uuid
        eval_payload_dict = {
            "evaluation_id": f"rre-{uuid.uuid4().hex[:12]}",
            "risk_analysis_uuid": risk_analysis_hex,
            "risk_analysis_version": request.risk_analysis_version,
            "initial_evaluation_uuid": request.initial_evaluation_uuid,
            "initial_evaluation_version": request.initial_evaluation_version,
            "residual_severity": request.residual_severity,
            "residual_probability": request.residual_probability,
            "calculated_risk_level": residual_level,
            "acceptable": comparison['acceptable'],
            "action_required": action_required,
            "severity_improved": comparison['severity_improved'],
            "probability_improved": comparison['probability_improved'],
            "severity_worsened": comparison['severity_worsened'],
            "probability_worsened": comparison['probability_worsened'],
            "risk_level_improved": comparison['risk_level_improved'],
            "reduced": comparison['reduced'],
            "regression_detected": comparison['regression_detected'],
            "benefit_risk_required": benefit_risk_required,
            "risk_policy_uuid": validated_ie.risk_policy_uuid,
            "risk_policy_version": validated_ie.risk_policy_version,
            "policy_revision": policy.version,
            "evaluator_user_id": request.evaluator_user_id,
            "rationale": request.rationale,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            validated_payload = ResidualRiskEvaluationPayload(**eval_payload_dict)
        except Exception as e:
            raise InvalidPersistedPayloadError(f"Invalid residual evaluation payload: {e}")

        # 11. Create evaluation object
        eval_obj, _ = self.repo.create_object(
            object_type='residual_risk_evaluation',
            payload=validated_payload.model_dump(),
            owner_user_id=request.evaluator_user_id,
            created_by=request.evaluator_user_id,
        )

        # 12. Create version-pinned relations using the EXACT requested versions
        self.repo.create_relation(
            source_uuid=eval_obj.object_uuid, source_version=eval_obj.current_version,
            target_uuid=ra_obj.object_uuid, target_version=request.risk_analysis_version,
            relation_type='residual_of', created_by=request.evaluator_user_id,
        )
        self.repo.create_relation(
            source_uuid=eval_obj.object_uuid, source_version=eval_obj.current_version,
            target_uuid=ie_obj.object_uuid, target_version=request.initial_evaluation_version,
            relation_type='derived_from_initial_evaluation', created_by=request.evaluator_user_id,
        )
        self.repo.create_relation(
            source_uuid=eval_obj.object_uuid, source_version=eval_obj.current_version,
            target_uuid=policy_obj.object_uuid, target_version=validated_ie.risk_policy_version,
            relation_type='uses_risk_policy', created_by=request.evaluator_user_id,
        )

        # 13. One atomic commit
        self.repo.session.commit()

        return {
            "object_uuid": eval_obj.uuid_hex,
            "object_version": eval_obj.current_version,
            "lifecycle_state": eval_obj.lifecycle_state,
            "payload": validated_payload.model_dump(),
        }
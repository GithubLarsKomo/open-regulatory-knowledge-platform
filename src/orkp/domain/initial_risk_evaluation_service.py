"""
Initial Risk Evaluation service for ORKP.

Persists the first deterministic risk evaluation referencing exact
RiskAnalysis and RiskPolicy versions.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    InvalidRelationError,
    InvalidPersistedPayloadError,
)
from orkp.domain.risk_models import (
    InitialRiskEvaluationCreateRequest,
    InitialRiskEvaluationPayload,
)
from orkp.domain.risk_evaluation import calculate_risk_level
from orkp.domain.versioned_loader import load_versioned_object, load_risk_policy


class InitialRiskEvaluationService:
    """Service for creating persisted Initial Risk Evaluations."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_evaluation(
        self,
        risk_analysis_hex: str,
        request: InitialRiskEvaluationCreateRequest,
    ) -> Dict[str, Any]:
        """Create a persisted Initial Risk Evaluation.

        Pins exact RiskAnalysis and RiskPolicy versions.
        Client must not supply derived fields.
        Uses one atomic transaction.

        Raises: ObjectNotFoundError, ObjectTypeMismatchError,
                ObjectVersionNotFoundError, InvalidLifecycleStateError,
                InvalidPersistedPayloadError, InvalidRelationError
        """
        # 1. Load RiskAnalysis with exact version and type check
        ra_obj, ra_payload = load_versioned_object(
            self.repo, risk_analysis_hex, request.risk_analysis_version,
            'risk_analysis',
        )

        # 2. Load RiskPolicy with exact version, type, lifecycle and payload validation
        policy_obj, policy_payload, policy = load_risk_policy(
            self.repo, request.risk_policy_uuid, request.risk_policy_version,
        )

        # 3. Validate severity and probability against the policy
        if request.severity not in policy.severity_scale:
            raise InvalidRelationError(
                f"Severity '{request.severity}' not in policy scale: {policy.severity_scale}"
            )
        if request.probability not in policy.probability_scale:
            raise InvalidRelationError(
                f"Probability '{request.probability}' not in policy scale: {policy.probability_scale}"
            )

        # 4. Calculate deterministic result
        result = calculate_risk_level(request.severity, request.probability, policy)
        action_required = policy.get_required_action(result['risk_level'])

        # 5. Build and validate payload
        import uuid
        eval_payload_dict = {
            "evaluation_id": f"ire-{uuid.uuid4().hex[:12]}",
            "risk_analysis_uuid": risk_analysis_hex,
            "risk_analysis_version": request.risk_analysis_version,
            "severity": request.severity,
            "probability": request.probability,
            "calculated_risk_level": result['risk_level'],
            "acceptable": result['acceptable'],
            "action_required": action_required,
            "risk_policy_uuid": request.risk_policy_uuid,
            "risk_policy_version": request.risk_policy_version,
            "policy_revision": policy.version,
            "evaluator_user_id": request.evaluator_user_id,
            "rationale": request.rationale,
            "assumptions": request.assumptions,
            "uncertainty": request.uncertainty,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            validated_payload = InitialRiskEvaluationPayload(**eval_payload_dict)
        except Exception as e:
            raise InvalidPersistedPayloadError(f"Invalid evaluation payload: {e}")

        # 6. Create evaluation object
        eval_obj, _ = self.repo.create_object(
            object_type='initial_risk_evaluation',
            payload=validated_payload.model_dump(),
            owner_user_id=request.evaluator_user_id,
            created_by=request.evaluator_user_id,
        )

        # 7. Create version-pinned relations
        self.repo.create_relation(
            source_uuid=eval_obj.object_uuid, source_version=eval_obj.current_version,
            target_uuid=ra_obj.object_uuid, target_version=request.risk_analysis_version,
            relation_type='evaluates_initial_risk_of', created_by=request.evaluator_user_id,
        )
        self.repo.create_relation(
            source_uuid=eval_obj.object_uuid, source_version=eval_obj.current_version,
            target_uuid=policy_obj.object_uuid, target_version=request.risk_policy_version,
            relation_type='uses_risk_policy', created_by=request.evaluator_user_id,
        )

        # 8. One atomic commit
        self.repo.session.commit()

        return {
            "object_uuid": eval_obj.uuid_hex,
            "object_version": eval_obj.current_version,
            "lifecycle_state": eval_obj.lifecycle_state,
            "payload": validated_payload.model_dump(),
        }
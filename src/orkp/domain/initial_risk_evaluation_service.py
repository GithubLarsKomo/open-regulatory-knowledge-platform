"""
Initial Risk Evaluation service for ORKP.

Persists the first deterministic risk evaluation referencing exact
RiskAnalysis and RiskPolicy versions. One atomic transaction.
"""

from datetime import datetime, timezone

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    InvalidRelationError,
    InvalidPersistedPayloadError,
)
from orkp.domain.risk_models import (
    InitialRiskEvaluationCreateRequest,
    InitialRiskEvaluationPayload,
    InitialRiskEvaluationResponse,
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
    ) -> InitialRiskEvaluationResponse:
        """Create a persisted Initial Risk Evaluation.

        Pins exact RiskAnalysis and RiskPolicy versions.
        Client must not supply derived fields.
        One atomic transaction.

        Raises: ObjectNotFoundError, ObjectTypeMismatchError,
                ObjectVersionNotFoundError, InvalidLifecycleStateError,
                InvalidPersistedPayloadError, InvalidRelationError
        """
        # 1. Load RiskAnalysis with exact version
        ra_loaded = load_versioned_object(
            self.repo,
            risk_analysis_hex,
            request.risk_analysis_version,
            "risk_analysis",
        )

        # 2. Load RiskPolicy with exact version, type, lifecycle, payload validation
        policy_loaded = load_risk_policy(
            self.repo,
            request.risk_policy_uuid,
            request.risk_policy_version,
        )

        policy = policy_loaded.policy

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
        action_required = policy.get_required_action(result["risk_level"])

        # 5. Build and validate payload
        import uuid

        eval_payload_dict = {
            "evaluation_id": f"ire-{uuid.uuid4().hex[:12]}",
            "risk_analysis_uuid": risk_analysis_hex,
            "risk_analysis_version": request.risk_analysis_version,
            "severity": request.severity,
            "probability": request.probability,
            "calculated_risk_level": result["risk_level"],
            "acceptable": result["acceptable"],
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

        from pydantic import ValidationError

        try:
            validated_payload = InitialRiskEvaluationPayload(**eval_payload_dict)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError("Invalid evaluation payload") from exc

        # 6. Create evaluation object and relations in one atomic transaction
        try:
            eval_obj, _ = self.repo.create_object(
                object_type="initial_risk_evaluation",
                payload=validated_payload.model_dump(),
                owner_user_id=request.evaluator_user_id,
                created_by=request.evaluator_user_id,
            )
            self.repo.create_relation(
                source_uuid=eval_obj.object_uuid,
                source_version=eval_obj.current_version,
                target_uuid=ra_loaded.object.object_uuid,
                target_version=request.risk_analysis_version,
                relation_type="evaluates_initial_risk_of",
                created_by=request.evaluator_user_id,
            )
            self.repo.create_relation(
                source_uuid=eval_obj.object_uuid,
                source_version=eval_obj.current_version,
                target_uuid=policy_loaded.object.object_uuid,
                target_version=request.risk_policy_version,
                relation_type="uses_risk_policy",
                created_by=request.evaluator_user_id,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return InitialRiskEvaluationResponse(
            object_uuid=eval_obj.uuid_hex,
            object_version=eval_obj.current_version,
            lifecycle_state=eval_obj.lifecycle_state,
            payload=validated_payload,
        )

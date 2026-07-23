"""
Initial Risk Evaluation service for ORKP.

Persists the first deterministic risk evaluation referencing an exact Risk Policy version.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    InvalidLifecycleTransitionError,
    RiskCompletenessError,
)
from orkp.domain.risk_evaluation import calculate_risk_level
from orkp.domain.risk_policy import default_risk_policy
from orkp.domain.risk_models import InitialRiskEvaluationCreateRequest


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

        Raises: ObjectNotFoundError, InvalidRelationError
        """
        ra = self.repo.get_by_uuid_hex(risk_analysis_hex)
        if ra is None:
            raise ObjectNotFoundError(f"Risk analysis {risk_analysis_hex} not found")

        policy_obj = self.repo.get_by_uuid_hex(request.risk_policy_uuid)
        if policy_obj is None:
            raise ObjectNotFoundError(f"Risk policy {request.risk_policy_uuid} not found")
        if policy_obj.lifecycle_state not in ('approved', 'effective'):
            raise InvalidLifecycleTransitionError(
                f"Risk policy {request.risk_policy_uuid} is {policy_obj.lifecycle_state}, need approved/effective"
            )

        policy_ver = self.repo.get_version(policy_obj.object_uuid, policy_obj.current_version)
        policy_payload = policy_ver.payload_json if policy_ver else {}

        # Calculate deterministic result
        from orkp.domain.risk_policy import RiskPolicy
        policy = RiskPolicy(
            severity_scale=policy_payload.get('severity_scale', []),
            probability_scale=policy_payload.get('probability_scale', []),
            risk_matrix=policy_payload.get('risk_matrix', {}),
            acceptability_rules=policy_payload.get('acceptability_rules', {}),
            control_hierarchy=policy_payload.get('control_hierarchy', []),
            benefit_risk_required_for_unacceptable=True,
        )
        result = calculate_risk_level(request.severity, request.probability, policy)

        # Create the evaluation object
        from orkp.db.models import _bin_to_str
        import uuid
        eval_payload = {
            "evaluation_id": f"ire-{uuid.uuid4().hex[:12]}",
            "risk_analysis_uuid": risk_analysis_hex,
            "risk_analysis_version": ra.current_version,
            "severity": request.severity,
            "probability": request.probability,
            "calculated_risk_level": result['risk_level'],
            "acceptable": result['acceptable'],
            "action_required": result['action_required'],
            "policy_uuid": request.risk_policy_uuid,
            "policy_version": policy_payload.get('policy_version', 'unknown'),
            "evaluator_user_id": request.evaluator_user_id,
            "rationale": request.rationale,
            "assumptions": request.assumptions,
            "uncertainty": request.uncertainty,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

        eval_obj, _ = self.repo.create_object(
            object_type='initial_risk_evaluation',
            payload=eval_payload,
            owner_user_id=request.evaluator_user_id,
            created_by=request.evaluator_user_id,
        )

        # Create relations
        self.repo.create_relation(
            source_uuid=eval_obj.object_uuid,
            source_version=eval_obj.current_version,
            target_uuid=ra.object_uuid,
            target_version=ra.current_version,
            relation_type='evaluates_initial_risk_of',
            created_by=request.evaluator_user_id,
        )
        self.repo.create_relation(
            source_uuid=eval_obj.object_uuid,
            source_version=eval_obj.current_version,
            target_uuid=policy_obj.object_uuid,
            target_version=policy_obj.current_version,
            relation_type='uses_risk_policy',
            created_by=request.evaluator_user_id,
        )

        self.repo.session.commit()
        return eval_payload
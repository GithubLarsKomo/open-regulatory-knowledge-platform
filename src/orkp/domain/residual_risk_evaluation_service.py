"""
Residual Risk Evaluation service for ORKP.

Persists the residual risk evaluation referencing exact initial evaluation
and risk policy versions.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    InvalidLifecycleTransitionError,
    InvalidRelationError,
)
from orkp.domain.risk_evaluation import (
    calculate_risk_level,
    compare_initial_and_residual_risk,
)
from orkp.domain.risk_models import ResidualRiskEvaluationCreateRequest
from orkp.domain.relation_policy import RELATION_SCHEMA


class ResidualRiskEvaluationService:
    """Service for creating persisted Residual Risk Evaluations."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def _build_risk_policy(self, policy_obj, policy_version):
        """Load a RiskPolicy from a persisted object version."""
        v = self.repo.get_version(policy_obj.object_uuid, policy_version)
        if v is None:
            raise ObjectNotFoundError(f"Risk policy version {policy_version} not found")
        p = v.payload_json or {}
        from orkp.domain.risk_policy import RiskPolicy
        return RiskPolicy(
            severity_scale=p.get('severity_scale', []),
            probability_scale=p.get('probability_scale', []),
            risk_matrix=p.get('risk_matrix', {}),
            acceptability_rules=p.get('acceptability_rules', {}),
            required_actions=p.get('required_actions', {}),
            control_hierarchy=p.get('control_hierarchy', []),
            benefit_risk_required_for_unacceptable=True,
        ), p.get('policy_version', 'unknown')

    def create_evaluation(
        self,
        risk_analysis_hex: str,
        request: ResidualRiskEvaluationCreateRequest,
    ) -> Dict[str, Any]:
        """Create a persisted Residual Risk Evaluation.

        Pins exact RiskAnalysis, InitialEvaluation, and RiskPolicy versions.
        """
        ra = self.repo.get_by_uuid_hex(risk_analysis_hex)
        if ra is None:
            raise ObjectNotFoundError(f"Risk analysis {risk_analysis_hex} not found")

        # Load and validate initial evaluation
        ie_obj = self.repo.get_by_uuid_hex(request.initial_evaluation_uuid)
        if ie_obj is None:
            raise ObjectNotFoundError(f"Initial evaluation {request.initial_evaluation_uuid} not found")
        if ie_obj.object_type != 'initial_risk_evaluation':
            raise InvalidRelationError(
                f"Expected initial_risk_evaluation, got {ie_obj.object_type}"
            )

        ie_version = self.repo.get_version(ie_obj.object_uuid, ie_obj.current_version)
        ie_payload = ie_version.payload_json if ie_version else {}

        # Verify initial evaluation belongs to this risk analysis
        if ie_payload.get('risk_analysis_uuid') != risk_analysis_hex:
            raise InvalidRelationError(
                "Initial evaluation does not belong to this risk analysis"
            )

        # Load the policy version pinned by the initial evaluation
        policy_uuid = ie_payload.get('policy_uuid', '')
        policy_version_str = ie_payload.get('policy_version', '')
        policy_obj = self.repo.get_by_uuid_hex(policy_uuid)
        if policy_obj is None:
            raise ObjectNotFoundError(f"Risk policy {policy_uuid} not found")

        # Convert stored policy_version (string) to int version_no for lookup
        policy = self._build_risk_policy(policy_obj, policy_obj.current_version)[0]

        # Calculate residual risk comparison
        initial_sev = ie_payload.get('severity', 'moderate')
        initial_prob = ie_payload.get('probability', 'possible')
        comparison = compare_initial_and_residual_risk(
            initial_sev, initial_prob,
            request.residual_severity, request.residual_probability,
            policy,
        )

        # Create the evaluation object
        import uuid
        eval_payload = {
            "evaluation_id": f"rre-{uuid.uuid4().hex[:12]}",
            "risk_analysis_uuid": risk_analysis_hex,
            "risk_analysis_version": ra.current_version,
            "initial_evaluation_uuid": request.initial_evaluation_uuid,
            "initial_evaluation_version": ie_obj.current_version,
            "residual_severity": request.residual_severity,
            "residual_probability": request.residual_probability,
            "calculated_risk_level": comparison['residual_risk']['risk_level'],
            "acceptable": comparison['acceptable'],
            "action_required": comparison['benefit_risk_required'] if not comparison['acceptable'] else 'none',
            "severity_improved": comparison['severity_improved'],
            "probability_improved": comparison['probability_improved'],
            "severity_worsened": comparison['severity_worsened'],
            "probability_worsened": comparison['probability_worsened'],
            "risk_level_improved": comparison['risk_level_improved'],
            "reduced": comparison['reduced'],
            "regression_detected": comparison['regression_detected'],
            "benefit_risk_required": comparison['benefit_risk_required'],
            "policy_uuid": policy_uuid,
            "policy_version": policy_version_str,
            "evaluator_user_id": request.evaluator_user_id,
            "rationale": request.rationale,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

        eval_obj, _ = self.repo.create_object(
            object_type='residual_risk_evaluation',
            payload=eval_payload,
            owner_user_id=request.evaluator_user_id,
            created_by=request.evaluator_user_id,
        )

        # Create relations
        self.repo.create_relation(
            source_uuid=eval_obj.object_uuid, source_version=eval_obj.current_version,
            target_uuid=ra.object_uuid, target_version=ra.current_version,
            relation_type='residual_of', created_by=request.evaluator_user_id,
        )
        self.repo.create_relation(
            source_uuid=eval_obj.object_uuid, source_version=eval_obj.current_version,
            target_uuid=ie_obj.object_uuid, target_version=ie_obj.current_version,
            relation_type='derived_from_initial_evaluation', created_by=request.evaluator_user_id,
        )
        self.repo.create_relation(
            source_uuid=eval_obj.object_uuid, source_version=eval_obj.current_version,
            target_uuid=policy_obj.object_uuid, target_version=policy_obj.current_version,
            relation_type='uses_risk_policy', created_by=request.evaluator_user_id,
        )

        self.repo.session.commit()
        return eval_payload
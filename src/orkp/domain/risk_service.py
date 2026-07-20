"""
Risk Management domain service for ORKP.

Implements the full risk management workflow per ISO 14971 principles.
Uses typed exceptions. No silent False/None returns.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from orkp.db.models import RegulatoryObject, _bin_to_str
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    InvalidLifecycleTransitionError,
    OptimisticLockError,
    InvalidRelationError,
    RiskCompletenessError,
    RiskEvaluationError,
    RiskControlVerificationError,
    AuthorizationError,
    SelfApprovalNotAllowedError,
)
from orkp.domain.risk_evaluation import (
    calculate_risk_level,
    compare_initial_and_residual_risk,
    evaluate_control_effectiveness,
)
from orkp.domain.risk_completeness import evaluate_risk_completeness
from orkp.domain.risk_policy import default_risk_policy
from orkp.domain.models import _bin_to_str as bin_to_str_hex


class RiskService:
    """Domain service for Risk Management objects."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    @staticmethod
    def _object_type() -> str:
        return 'risk_analysis'

    # ------------------------------------------------------------------
    # Create risk chain elements
    # ------------------------------------------------------------------

    def create_object(self, object_type: str, payload: Dict[str, Any], owner_user_id: str, created_by: str) -> Tuple[RegulatoryObject, Any]:
        return self.repo.create_object(
            object_type=object_type, payload=payload,
            owner_user_id=owner_user_id, created_by=created_by,
        )

    def create_hazard(self, payload: Dict[str, Any], owner_user_id: str) -> RegulatoryObject:
        obj, _ = self.create_object('hazard', payload, owner_user_id, owner_user_id)
        self.repo.session.commit()
        return obj

    def create_sequence_of_events(self, payload: Dict[str, Any], owner_user_id: str) -> RegulatoryObject:
        obj, _ = self.create_object('sequence_of_events', payload, owner_user_id, owner_user_id)
        self.repo.session.commit()
        return obj

    def create_hazardous_situation(self, payload: Dict[str, Any], owner_user_id: str) -> RegulatoryObject:
        obj, _ = self.create_object('hazardous_situation', payload, owner_user_id, owner_user_id)
        self.repo.session.commit()
        return obj

    def create_harm(self, payload: Dict[str, Any], owner_user_id: str) -> RegulatoryObject:
        obj, _ = self.create_object('harm', payload, owner_user_id, owner_user_id)
        self.repo.session.commit()
        return obj

    def create_risk_analysis(self, payload: Dict[str, Any], owner_user_id: str) -> RegulatoryObject:
        obj, _ = self.create_object('risk_analysis', payload, owner_user_id, owner_user_id)
        self.repo.session.commit()
        return obj

    def create_risk_control(self, payload: Dict[str, Any], owner_user_id: str) -> RegulatoryObject:
        obj, _ = self.create_object('risk_control', payload, owner_user_id, owner_user_id)
        self.repo.session.commit()
        return obj

    def create_benefit_risk_analysis(self, payload: Dict[str, Any], owner_user_id: str) -> RegulatoryObject:
        obj, _ = self.create_object('benefit_risk', payload, owner_user_id, owner_user_id)
        self.repo.session.commit()
        return obj

    # ------------------------------------------------------------------
    # Relations
    # ------------------------------------------------------------------

    def _rel(self, source_hex: str, target_hex: str, rel_type: str, created_by: str) -> None:
        source = self.repo.get_by_uuid_hex(source_hex)
        target = self.repo.get_by_uuid_hex(target_hex)
        if source is None:
            raise ObjectNotFoundError(f"Source {source_hex} not found")
        if target is None:
            raise ObjectNotFoundError(f"Target {target_hex} not found")
        self.repo.create_relation(
            source_uuid=source.object_uuid,
            source_version=source.current_version,
            target_uuid=target.object_uuid,
            target_version=target.current_version,
            relation_type=rel_type,
            created_by=created_by,
        )

    def link_risk_chain(self, hazard_hex: str, sequence_hex: str, situation_hex: str, harm_hex: str, created_by: str) -> None:
        """Link the full hazard chain: hazard -> sequence -> situation -> harm."""
        self._rel(hazard_hex, sequence_hex, 'originates_from', created_by)
        self._rel(sequence_hex, situation_hex, 'creates_situation', created_by)
        self._rel(situation_hex, harm_hex, 'may_cause', created_by)
        self.repo.session.commit()

    def estimate_initial_risk(self, risk_analysis_hex: str, situation_hex: str, created_by: str) -> None:
        self._rel(risk_analysis_hex, situation_hex, 'estimated_by', created_by)
        self.repo.session.commit()

    def link_risk_to_product(self, risk_analysis_hex: str, product_hex: str, created_by: str) -> None:
        self._rel(risk_analysis_hex, product_hex, 'applies_to_product', created_by)
        self.repo.session.commit()

    def add_risk_control(self, risk_analysis_hex: str, control_hex: str, created_by: str) -> None:
        self._rel(risk_analysis_hex, control_hex, 'controlled_by', created_by)
        self.repo.session.commit()

    def link_control_verification(self, control_hex: str, evidence_hex: str, created_by: str) -> None:
        self._rel(control_hex, evidence_hex, 'control_verified_by', created_by)
        self.repo.session.commit()

    def estimate_residual_risk(self, risk_analysis_hex: str, residual_risk_hex: str, created_by: str) -> None:
        self._rel(risk_analysis_hex, residual_risk_hex, 'residual_of', created_by)
        self.repo.session.commit()

    # ------------------------------------------------------------------
    # Risk evaluation
    # ------------------------------------------------------------------

    def evaluate_risk(self, risk_analysis_hex: str) -> Dict[str, Any]:
        """Evaluate initial risk from payload."""
        obj = self.repo.get_by_uuid_hex(risk_analysis_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Risk analysis {risk_analysis_hex} not found")
        v = self.repo.get_version(obj.object_uuid, obj.current_version)
        payload = v.payload_json if v else {}
        sev = payload.get('severity', 'moderate')
        prob = payload.get('probability', 'possible')
        return calculate_risk_level(sev, prob)

    def evaluate_residual_risk(self, risk_analysis_hex: str, residual_severity: str, residual_probability: str) -> Dict[str, Any]:
        """Compare initial and residual risk."""
        obj = self.repo.get_by_uuid_hex(risk_analysis_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Risk analysis {risk_analysis_hex} not found")
        v = self.repo.get_version(obj.object_uuid, obj.current_version)
        payload = v.payload_json if v else {}
        initial_sev = payload.get('severity', 'moderate')
        initial_prob = payload.get('probability', 'possible')
        return compare_initial_and_residual_risk(
            initial_sev, initial_prob, residual_severity, residual_probability,
        )

    def evaluate_control_verification(self, control_hex: str) -> Dict[str, Any]:
        """Evaluate whether a risk control has approved verification."""
        obj = self.repo.get_by_uuid_hex(control_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Risk control {control_hex} not found")
        v = self.repo.get_version(obj.object_uuid, obj.current_version)
        payload = v.payload_json if v else {}
        status = payload.get('implementation_status', 'proposed')
        ver_req = payload.get('verification_required', True)
        # Find active verification evidence
        rels = self.repo.list_active_relations_for_source(obj.object_uuid)
        has_approved = False
        for r in rels:
            if r.relation_type == 'control_verified_by':
                ev = self.repo.get_by_uuid(r.target_uuid)
                if ev and ev.lifecycle_state == 'approved':
                    ev_v = self.repo.get_version(r.target_uuid, r.target_version)
                    if ev_v and ev_v.status == 'approved':
                        has_approved = True
                        break
        return evaluate_control_effectiveness(status, ver_req, has_approved)

    # ------------------------------------------------------------------
    # Completeness and approval
    # ------------------------------------------------------------------

    def evaluate_risk_completeness(self, risk_analysis_hex: str) -> Dict[str, Any]:
        """Evaluate completeness for approval."""
        obj = self.repo.get_by_uuid_hex(risk_analysis_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Risk analysis {risk_analysis_hex} not found")

        all_rels = self.repo.list_all_relations_for_source(obj.object_uuid)
        has_hazard = any(r.relation_type == 'estimated_by' for r in all_rels if r.lifecycle_state == 'active')
        has_controls = any(r.relation_type == 'controlled_by' for r in all_rels if r.lifecycle_state == 'active')
        has_product = any(r.relation_type == 'applies_to_product' for r in all_rels if r.lifecycle_state == 'active')

        # Check chain completeness
        chain_rels = self.repo.list_all_relations_for_target(obj.object_uuid)
        has_sequence = any(r.relation_type == 'originates_from' for r in chain_rels)
        has_situation = any(r.relation_type == 'creates_situation' for r in chain_rels)
        has_harm = any(r.relation_type == 'may_cause' for r in chain_rels)

        # Check controls verification
        controls_verified = True
        for r in all_rels:
            if r.relation_type == 'controlled_by' and r.lifecycle_state == 'active':
                ctrl = self.repo.get_by_uuid(r.target_uuid)
                if ctrl:
                    cv = self.repo.get_version(ctrl.object_uuid, ctrl.current_version)
                    cp = cv.payload_json if cv else {}
                    if cp.get('verification_required', True):
                        ctrl_rels = self.repo.list_active_relations_for_source(ctrl.object_uuid)
                        has_ev = any(
                            rr.relation_type == 'control_verified_by'
                            for rr in ctrl_rels
                        )
                        if not has_ev:
                            controls_verified = False

        # Check residual
        has_residual = any(r.relation_type == 'residual_of' for r in all_rels if r.lifecycle_state == 'active')
        residual_acceptable = True
        benefit_risk_approved = False

        if has_residual:
            for r in all_rels:
                if r.relation_type == 'residual_of' and r.lifecycle_state == 'active':
                    res = self.repo.get_by_uuid(r.target_uuid)
                    if res:
                        rv = self.repo.get_version(res.object_uuid, res.current_version)
                        rp = rv.payload_json if rv else {}
                        acc = rp.get('acceptability', 'acceptable')
                        residual_acceptable = (acc == 'acceptable' or acc == 'as_low_as_reasonably_practicable')
                        # Check benefit-risk
                        br_rels = self.repo.list_active_relations_for_target(res.object_uuid)
                        benefit_risk_approved = any(
                            br.relation_type == 'benefit_risk_for'
                            for br in br_rels
                        )

        return evaluate_risk_completeness(
            risk_analysis_hex, has_hazard, has_sequence, has_situation,
            has_harm, has_product, has_controls, controls_verified,
            has_residual, residual_acceptable, benefit_risk_approved,
        )

    def submit_for_review(self, risk_analysis_hex: str, actor_user_id: str) -> None:
        obj = self.repo.get_by_uuid_hex(risk_analysis_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Risk analysis {risk_analysis_hex} not found")
        self.repo.transition_state(obj.object_uuid, 'in_review', actor_user_id)
        self.repo.session.commit()

    def approve_risk(self, risk_analysis_hex: str, approver_user_id: str, created_by: str, comments: Optional[str] = None) -> None:
        """Approve only if completeness passes and no self-approval."""
        obj = self.repo.get_by_uuid_hex(risk_analysis_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Risk analysis {risk_analysis_hex} not found")
        if obj.owner_user_id == approver_user_id:
            raise SelfApprovalNotAllowedError("Risk author cannot approve own analysis")
        completeness = self.evaluate_risk_completeness(risk_analysis_hex)
        if not completeness['complete']:
            raise RiskCompletenessError(
                "Risk approval blocked: " + "; ".join(completeness['blocking_issues'])
            )
        self.repo.transition_state(obj.object_uuid, 'approved', approver_user_id, comments)
        self.repo.session.commit()

    def reject_risk(self, risk_analysis_hex: str, reviewer_user_id: str, comments: str) -> None:
        obj = self.repo.get_by_uuid_hex(risk_analysis_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Risk analysis {risk_analysis_hex} not found")
        self.repo.transition_state(obj.object_uuid, 'rejected', reviewer_user_id, comments)
        self.repo.session.commit()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_traceability(self, risk_analysis_hex: str) -> List[Dict[str, Any]]:
        obj = self.repo.get_by_uuid_hex(risk_analysis_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Risk analysis {risk_analysis_hex} not found")
        results = []
        all_rels = self.repo.list_all_relations_for_source(obj.object_uuid)
        for r in all_rels:
            results.append({
                "relation_uuid": _bin_to_str(r.relation_uuid),
                "relation_type": r.relation_type,
                "relation_state": r.lifecycle_state,
                "target_uuid": _bin_to_str(r.target_uuid),
                "target_version": r.target_version,
            })
        return results

    def get_impact(self, object_hex: str) -> Dict[str, Any]:
        """Find all risk analyses affected by a change to this object."""
        obj = self.repo.get_by_uuid_hex(object_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Object {object_hex} not found")
        rels = self.repo.list_active_relations_for_source(obj.object_uuid)
        affected_risks = []
        for r in rels:
            if r.relation_type in ('controlled_by', 'estimated_by', 'applies_to_product'):
                target = self.repo.get_by_uuid(r.target_uuid)
                if target:
                    affected_risks.append({
                        "risk_uuid": target.uuid_hex,
                        "risk_type": target.object_type,
                        "relation_type": r.relation_type,
                    })
        return {
            "changed_object_uuid": object_hex,
            "affected_risk_count": len(affected_risks),
            "affected_risks": affected_risks,
            "rule_codes": ["RISK-IMPACT-CHANGE-001"] if affected_risks else [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
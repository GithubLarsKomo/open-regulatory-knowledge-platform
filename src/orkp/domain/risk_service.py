"""
Risk Management domain service for ORKP.

Implements the full risk management workflow per ISO 14971 principles.
Uses typed exceptions, canonical relations, and atomic transactions.
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


# Canonical relation direction schema
RELATION_SCHEMA = {
    'has_hazard': ('risk_analysis', 'hazard'),
    'followed_by': ('hazard', 'sequence_of_events'),
    'creates_situation': ('sequence_of_events', 'hazardous_situation'),
    'may_cause': ('hazardous_situation', 'harm'),
    'estimated_for': ('risk_analysis', 'hazardous_situation'),
    'controlled_by': ('risk_analysis', 'risk_control'),
    'verifies_control': ('evidence', 'risk_control'),
    'supports_verification': ('evidence', 'control_verification'),
    'residual_of': ('residual_risk', 'risk_analysis'),
    'benefit_risk_for': ('benefit_risk', 'residual_risk'),
    'overall_risk_for': ('overall_residual_risk', 'product'),
    'applies_to_product': ('risk_analysis', 'product'),
    'applies_to_device': ('risk_analysis', 'device'),
}


class RiskService:
    """Domain service for Risk Management objects."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def _validate_rel(self, source_type: str, rel_type: str, target_type: str) -> None:
        schema = RELATION_SCHEMA.get(rel_type)
        if schema is None:
            raise InvalidRelationError(f"Unknown relation type '{rel_type}'")
        expected_src, expected_tgt = schema
        if source_type != expected_src:
            raise InvalidRelationError(
                f"Relation '{rel_type}' requires source type '{expected_src}', got '{source_type}'"
            )
        if target_type != expected_tgt:
            raise InvalidRelationError(
                f"Relation '{rel_type}' requires target type '{expected_tgt}', got '{target_type}'"
            )

    def _rel(self, source_hex: str, target_hex: str, rel_type: str, created_by: str) -> None:
        source = self.repo.get_by_uuid_hex(source_hex)
        target = self.repo.get_by_uuid_hex(target_hex)
        if source is None:
            raise ObjectNotFoundError(f"Source {source_hex} not found")
        if target is None:
            raise ObjectNotFoundError(f"Target {target_hex} not found")
        self._validate_rel(source.object_type, rel_type, target.object_type)
        self.repo.create_relation(
            source_uuid=source.object_uuid,
            source_version=source.current_version,
            target_uuid=target.object_uuid,
            target_version=target.current_version,
            relation_type=rel_type,
            created_by=created_by,
        )

    # ------------------------------------------------------------------
    # Create objects
    # ------------------------------------------------------------------

    def create_object(self, object_type: str, payload: Dict[str, Any], owner_user_id: str) -> RegulatoryObject:
        obj, _ = self.repo.create_object(
            object_type=object_type, payload=payload,
            owner_user_id=owner_user_id, created_by=owner_user_id,
        )
        self.repo.session.commit()
        return obj

    # ------------------------------------------------------------------
    # Atomic risk chain creation
    # ------------------------------------------------------------------

    def create_risk_chain(
        self,
        risk_analysis_hex: str,
        hazard_hex: str,
        sequence_hex: str,
        situation_hex: str,
        harm_hex: str,
        actor_user_id: str,
    ) -> None:
        """Atomically create the full risk chain with canonical relations.

        Validates all objects exist and pins current versions.
        Rolls back on any failure.
        """
        ra = self.repo.get_by_uuid_hex(risk_analysis_hex)
        hz = self.repo.get_by_uuid_hex(hazard_hex)
        sq = self.repo.get_by_uuid_hex(sequence_hex)
        si = self.repo.get_by_uuid_hex(situation_hex)
        hm = self.repo.get_by_uuid_hex(harm_hex)
        for name, obj in [('risk_analysis', ra), ('hazard', hz), ('sequence_of_events', sq),
                          ('hazardous_situation', si), ('harm', hm)]:
            if obj is None:
                raise ObjectNotFoundError(f"{name} not found")
            if obj.object_type != name:
                raise InvalidRelationError(f"Expected {name}, got {obj.object_type} for {name}")

        self._rel(risk_analysis_hex, hazard_hex, 'has_hazard', actor_user_id)
        self._rel(hazard_hex, sequence_hex, 'followed_by', actor_user_id)
        self._rel(sequence_hex, situation_hex, 'creates_situation', actor_user_id)
        self._rel(situation_hex, harm_hex, 'may_cause', actor_user_id)
        self._rel(risk_analysis_hex, situation_hex, 'estimated_for', actor_user_id)
        self.repo.session.commit()

    # ------------------------------------------------------------------
    # Individual relations
    # ------------------------------------------------------------------

    def link_risk_to_product(self, risk_analysis_hex: str, product_hex: str, created_by: str) -> None:
        self._rel(risk_analysis_hex, product_hex, 'applies_to_product', created_by)
        self.repo.session.commit()

    def add_risk_control(self, risk_analysis_hex: str, control_hex: str, created_by: str) -> None:
        self._rel(risk_analysis_hex, control_hex, 'controlled_by', created_by)
        self.repo.session.commit()

    def link_control_verification(self, evidence_hex: str, control_hex: str, created_by: str) -> None:
        self._rel(evidence_hex, control_hex, 'verifies_control', created_by)
        self.repo.session.commit()

    # ------------------------------------------------------------------
    # Risk evaluation
    # ------------------------------------------------------------------

    def evaluate_risk(self, risk_analysis_hex: str) -> Dict[str, Any]:
        obj = self.repo.get_by_uuid_hex(risk_analysis_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Risk analysis {risk_analysis_hex} not found")
        v = self.repo.get_version(obj.object_uuid, obj.current_version)
        payload = v.payload_json if v else {}
        return calculate_risk_level(
            payload.get('severity', 'moderate'),
            payload.get('probability', 'possible'),
        )

    def evaluate_residual_risk(self, risk_analysis_hex: str, residual_severity: str, residual_probability: str) -> Dict[str, Any]:
        obj = self.repo.get_by_uuid_hex(risk_analysis_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Risk analysis {risk_analysis_hex} not found")
        v = self.repo.get_version(obj.object_uuid, obj.current_version)
        payload = v.payload_json if v else {}
        return compare_initial_and_residual_risk(
            payload.get('severity', 'moderate'), payload.get('probability', 'possible'),
            residual_severity, residual_probability,
        )

    # ------------------------------------------------------------------
    # Completeness and approval
    # ------------------------------------------------------------------

    def evaluate_risk_completeness(self, risk_analysis_hex: str) -> Dict[str, Any]:
        obj = self.repo.get_by_uuid_hex(risk_analysis_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Risk analysis {risk_analysis_hex} not found")

        all_rels = self.repo.list_all_relations_for_source(obj.object_uuid)
        active_rels = [r for r in all_rels if r.lifecycle_state == 'active']

        has_hazard = any(r.relation_type == 'has_hazard' for r in active_rels)
        has_controls = any(r.relation_type == 'controlled_by' for r in active_rels)
        has_product = any(r.relation_type == 'applies_to_product' for r in active_rels)

        # Find hazard -> chain
        has_sequence = False
        has_situation = False
        has_harm = False
        for r in active_rels:
            if r.relation_type == 'has_hazard':
                hazard_rels = self.repo.list_active_relations_for_source(r.target_uuid)
                for hr in hazard_rels:
                    if hr.relation_type == 'followed_by':
                        has_sequence = True
                        seq_rels = self.repo.list_active_relations_for_source(hr.target_uuid)
                        for sr in seq_rels:
                            if sr.relation_type == 'creates_situation':
                                has_situation = True
                                sit_rels = self.repo.list_active_relations_for_source(sr.target_uuid)
                                for sir in sit_rels:
                                    if sir.relation_type == 'may_cause':
                                        has_harm = True

        # Controls verification
        controls_verified = True
        for r in active_rels:
            if r.relation_type == 'controlled_by':
                ctrl = self.repo.get_by_uuid(r.target_uuid)
                if ctrl:
                    cv = self.repo.get_version(ctrl.object_uuid, ctrl.current_version)
                    cp = cv.payload_json if cv else {}
                    if cp.get('verification_required', True):
                        ctrl_rels = self.repo.list_active_relations_for_source(ctrl.object_uuid)
                        has_ev = any(rr.relation_type == 'verifies_control' for rr in ctrl_rels)
                        if not has_ev:
                            controls_verified = False

        # Residual
        has_residual = any(r.relation_type == 'residual_of' for r in active_rels)
        residual_acceptable = True
        benefit_risk_approved = False
        if has_residual:
            for r in active_rels:
                if r.relation_type == 'residual_of':
                    res = self.repo.get_by_uuid(r.target_uuid)
                    if res:
                        rv = self.repo.get_version(res.object_uuid, res.current_version)
                        rp = rv.payload_json if rv else {}
                        acc = rp.get('acceptability', 'acceptable')
                        residual_acceptable = (acc == 'acceptable' or acc == 'as_low_as_reasonably_practicable')
                        br_rels = self.repo.list_active_relations_for_target(res.object_uuid)
                        benefit_risk_approved = any(br.relation_type == 'benefit_risk_for' for br in br_rels)

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
    # Traceability
    # ------------------------------------------------------------------

    def get_traceability(self, risk_analysis_hex: str) -> List[Dict[str, Any]]:
        obj = self.repo.get_by_uuid_hex(risk_analysis_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Risk analysis {risk_analysis_hex} not found")

        results = []
        processed = set()

        def add_relations(uuid_hex: str, depth: int = 0):
            if depth > 5 or uuid_hex in processed:
                return
            processed.add(uuid_hex)
            obj_uuid = uuid.UUID(hex=uuid_hex).bytes
            for rels, direction in [
                (self.repo.list_all_relations_for_source(obj_uuid), 'outgoing'),
                (self.repo.list_all_relations_for_target(obj_uuid), 'incoming'),
            ]:
                for r in rels:
                    src = _bin_to_str(r.source_uuid)
                    tgt = _bin_to_str(r.target_uuid)
                    src_obj = self.repo.get_by_uuid(r.source_uuid)
                    tgt_obj = self.repo.get_by_uuid(r.target_uuid)
                    results.append({
                        "relation_uuid": _bin_to_str(r.relation_uuid),
                        "relation_type": r.relation_type,
                        "lifecycle_state": r.lifecycle_state,
                        "source_uuid": src,
                        "source_version": r.source_version,
                        "source_object_type": src_obj.object_type if src_obj else 'unknown',
                        "target_uuid": tgt,
                        "target_version": r.target_version,
                        "target_object_type": tgt_obj.object_type if tgt_obj else 'unknown',
                        "direction": direction,
                    })
                    if direction == 'outgoing':
                        add_relations(tgt, depth + 1)

        import uuid
        add_relations(risk_analysis_hex)
        return results

    def get_impact(self, object_hex: str) -> Dict[str, Any]:
        obj = self.repo.get_by_uuid_hex(object_hex)
        if obj is None:
            raise ObjectNotFoundError(f"Object {object_hex} not found")
        rels = self.repo.list_active_relations_for_source(obj.object_uuid)
        affected_risks = []
        for r in rels:
            if r.relation_type in ('controlled_by', 'estimated_for', 'applies_to_product', 'has_hazard', 'followed_by',
                                    'creates_situation', 'may_cause'):
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
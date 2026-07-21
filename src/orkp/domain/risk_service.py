"""
Risk Management domain service for ORKP.

Implements the full risk management workflow per ISO 14971 principles.
Uses typed exceptions, canonical relations, and atomic transactions.
"""

import uuid
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
    SelfApprovalNotAllowedError,
)
from orkp.domain.risk_evaluation import (
    calculate_risk_level,
    compare_initial_and_residual_risk,
    evaluate_control_effectiveness,
)
from orkp.domain.risk_completeness import evaluate_risk_completeness
from orkp.domain.risk_policy import default_risk_policy


class RiskService:
    """Domain service for Risk Management objects."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

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
        self, ra_hex: str, hz_hex: str, sq_hex: str, si_hex: str, hm_hex: str, actor: str,
    ) -> None:
        for name, h in [('risk_analysis', ra_hex), ('hazard', hz_hex),
                        ('sequence_of_events', sq_hex), ('hazardous_situation', si_hex), ('harm', hm_hex)]:
            o = self.repo.get_by_uuid_hex(h)
            if o is None:
                raise ObjectNotFoundError(f"{name} {h} not found")
            if o.object_type != name:
                raise InvalidRelationError(f"Expected {name}, got {o.object_type}")
        self._rel(ra_hex, hz_hex, 'has_hazard', actor)
        self._rel(hz_hex, sq_hex, 'followed_by', actor)
        self._rel(sq_hex, si_hex, 'creates_situation', actor)
        self._rel(si_hex, hm_hex, 'may_cause', actor)
        self._rel(ra_hex, si_hex, 'estimated_for', actor)
        self.repo.session.commit()

    def link_risk_to_product(self, ra_hex: str, prod_hex: str, actor: str) -> None:
        self._rel(ra_hex, prod_hex, 'applies_to_product', actor)
        self.repo.session.commit()

    def add_risk_control(self, ra_hex: str, ctrl_hex: str, actor: str) -> None:
        self._rel(ra_hex, ctrl_hex, 'controlled_by', actor)
        self.repo.session.commit()

    def link_control_verification(self, ev_hex: str, ctrl_hex: str, actor: str) -> None:
        self._rel(ev_hex, ctrl_hex, 'verifies_control', actor)
        self.repo.session.commit()

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate_risk(self, ra_hex: str) -> Dict[str, Any]:
        o = self.repo.get_by_uuid_hex(ra_hex)
        if o is None:
            raise ObjectNotFoundError(f"Risk analysis {ra_hex} not found")
        v = self.repo.get_version(o.object_uuid, o.current_version)
        p = v.payload_json if v else {}
        return calculate_risk_level(p.get('severity', 'moderate'), p.get('probability', 'possible'))

    def evaluate_residual_risk(self, ra_hex: str, rsev: str, rprob: str) -> Dict[str, Any]:
        o = self.repo.get_by_uuid_hex(ra_hex)
        if o is None:
            raise ObjectNotFoundError(f"Risk analysis {ra_hex} not found")
        v = self.repo.get_version(o.object_uuid, o.current_version)
        p = v.payload_json if v else {}
        return compare_initial_and_residual_risk(
            p.get('severity', 'moderate'), p.get('probability', 'possible'), rsev, rprob,
        )

    # ------------------------------------------------------------------
    # Completeness traversal — uses canonical direction model
    # ------------------------------------------------------------------

    def evaluate_risk_completeness(self, ra_hex: str) -> Dict[str, Any]:
        o = self.repo.get_by_uuid_hex(ra_hex)
        if o is None:
            raise ObjectNotFoundError(f"Risk analysis {ra_hex} not found")

        outgoing = self.repo.list_active_relations_for_source(o.object_uuid)
        incoming = self.repo.list_active_relations_for_target(o.object_uuid)

        has_hazard = any(r.relation_type == 'has_hazard' for r in outgoing)
        has_product = any(r.relation_type == 'applies_to_product' for r in outgoing)
        has_controls = any(r.relation_type == 'controlled_by' for r in outgoing)

        # Traverse hazard chain via outgoing: has_hazard -> followed_by -> creates_situation -> may_cause
        has_sequence = has_situation = has_harm = False
        for r in outgoing:
            if r.relation_type == 'has_hazard':
                hr = self.repo.list_active_relations_for_source(r.target_uuid)
                for h in hr:
                    if h.relation_type == 'followed_by':
                        has_sequence = True
                        sr = self.repo.list_active_relations_for_source(h.target_uuid)
                        for s in sr:
                            if s.relation_type == 'creates_situation':
                                has_situation = True
                                sir = self.repo.list_active_relations_for_source(s.target_uuid)
                                for si in sir:
                                    if si.relation_type == 'may_cause':
                                        has_harm = True

        # Controls verification: controlled_by (outgoing) -> verifies_control (incoming for RiskControl)
        controls_verified = True
        for r in outgoing:
            if r.relation_type == 'controlled_by':
                ctrl = self.repo.get_by_uuid(r.target_uuid)
                if ctrl:
                    cv = self.repo.get_version(ctrl.object_uuid, ctrl.current_version)
                    cp = cv.payload_json if cv else {}
                    if cp.get('verification_required', True):
                        # verifies_control comes IN to RiskControl, so check incoming
                        ctrl_incoming = self.repo.list_active_relations_for_target(ctrl.object_uuid)
                        has_ev = any(rr.relation_type == 'verifies_control' for rr in ctrl_incoming)
                        if not has_ev:
                            controls_verified = False

        # Residual: residual_of comes IN to RiskAnalysis
        has_residual = any(r.relation_type == 'residual_of' for r in incoming)
        residual_acceptable = False  # Never default to acceptable
        benefit_risk_approved = False
        if has_residual:
            for r in incoming:
                if r.relation_type == 'residual_of':
                    res = self.repo.get_by_uuid(r.source_uuid)
                    if res:
                        rv = self.repo.get_version(res.object_uuid, res.current_version)
                        rp = rv.payload_json if rv else {}
                        acc = rp.get('acceptability', '')
                        residual_acceptable = (acc == 'acceptable' or acc == 'as_low_as_reasonably_practicable')
                        # benefit_risk_for comes IN to ResidualRisk
                        br_incoming = self.repo.list_active_relations_for_target(res.object_uuid)
                        for br in br_incoming:
                            if br.relation_type == 'benefit_risk_for':
                                ba = self.repo.get_by_uuid(br.source_uuid)
                                if ba and ba.lifecycle_state == 'approved':
                                    bv = self.repo.get_version(ba.object_uuid, ba.current_version)
                                    bp = bv.payload_json if bv else {}
                                    benefit_risk_approved = (bp.get('conclusion') == 'favorable')

        return evaluate_risk_completeness(
            ra_hex, has_hazard, has_sequence, has_situation, has_harm, has_product,
            has_controls, controls_verified, has_residual, residual_acceptable, benefit_risk_approved,
        )

    def submit_for_review(self, ra_hex: str, actor: str) -> None:
        o = self.repo.get_by_uuid_hex(ra_hex)
        if o is None:
            raise ObjectNotFoundError(f"Risk analysis {ra_hex} not found")
        self.repo.transition_state(o.object_uuid, 'in_review', actor)
        self.repo.session.commit()

    def approve_risk(self, ra_hex: str, approver: str, created_by: str, comments: Optional[str] = None) -> None:
        o = self.repo.get_by_uuid_hex(ra_hex)
        if o is None:
            raise ObjectNotFoundError(f"Risk analysis {ra_hex} not found")
        if o.owner_user_id == approver:
            raise SelfApprovalNotAllowedError("Risk author cannot approve own analysis")
        c = self.evaluate_risk_completeness(ra_hex)
        if not c['complete']:
            raise RiskCompletenessError("Risk approval blocked: " + "; ".join(c['blocking_issues']))
        self.repo.transition_state(o.object_uuid, 'approved', approver, comments)
        self.repo.session.commit()

    def reject_risk(self, ra_hex: str, reviewer: str, comments: str) -> None:
        o = self.repo.get_by_uuid_hex(ra_hex)
        if o is None:
            raise ObjectNotFoundError(f"Risk analysis {ra_hex} not found")
        self.repo.transition_state(o.object_uuid, 'rejected', reviewer, comments)
        self.repo.session.commit()

    # ------------------------------------------------------------------
    # Traceability — cycle-safe recursive graph traversal
    # ------------------------------------------------------------------

    def get_traceability(self, ra_hex: str) -> List[Dict[str, Any]]:
        o = self.repo.get_by_uuid_hex(ra_hex)
        if o is None:
            raise ObjectNotFoundError(f"Risk analysis {ra_hex} not found")
        edges = []
        seen = set()

        def _walk(node_hex: str, depth: int = 0):
            if depth > 6 or node_hex in seen:
                return
            seen.add(node_hex)
            node_uuid = uuid.UUID(hex=node_hex).bytes
            for rels, direction in [
                (self.repo.list_all_relations_for_source(node_uuid), 'outgoing'),
                (self.repo.list_all_relations_for_target(node_uuid), 'incoming'),
            ]:
                for r in rels:
                    src = _bin_to_str(r.source_uuid)
                    tgt = _bin_to_str(r.target_uuid)
                    src_o = self.repo.get_by_uuid(r.source_uuid)
                    tgt_o = self.repo.get_by_uuid(r.target_uuid)
                    edges.append({
                        "relation_uuid": _bin_to_str(r.relation_uuid),
                        "relation_type": r.relation_type,
                        "lifecycle_state": r.lifecycle_state,
                        "source_uuid": src, "source_version": r.source_version,
                        "source_object_type": src_o.object_type if src_o else 'unknown',
                        "target_uuid": tgt, "target_version": r.target_version,
                        "target_object_type": tgt_o.object_type if tgt_o else 'unknown',
                        "direction": direction,
                    })
                    if direction == 'outgoing':
                        _walk(tgt, depth + 1)
        _walk(ra_hex)
        return edges

    def get_impact(self, obj_hex: str) -> Dict[str, Any]:
        o = self.repo.get_by_uuid_hex(obj_hex)
        if o is None:
            raise ObjectNotFoundError(f"Object {obj_hex} not found")
        rels = self.repo.list_active_relations_for_source(o.object_uuid)
        affected = []
        for r in rels:
            if r.relation_type in ('controlled_by', 'estimated_for', 'applies_to_product', 'has_hazard',
                                    'followed_by', 'creates_situation', 'may_cause'):
                t = self.repo.get_by_uuid(r.target_uuid)
                if t:
                    affected.append({"risk_uuid": t.uuid_hex, "risk_type": t.object_type, "relation_type": r.relation_type})
        return {
            "changed_object_uuid": obj_hex, "affected_risk_count": len(affected),
            "affected_risks": affected, "rule_codes": ["RISK-IMPACT-CHANGE-001"] if affected else [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
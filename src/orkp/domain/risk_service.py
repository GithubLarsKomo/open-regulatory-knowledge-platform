"""
Risk Management domain service for ORKP.

Implements the full risk management workflow per ISO 14971 principles.
Uses typed exceptions, canonical relations, and atomic transactions.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from orkp.db.models import RegulatoryObject, _bin_to_str
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.benefit_risk_models import BenefitRiskAnalysisPayload
from orkp.domain.control_verification_service import ControlVerificationService
from orkp.domain.exceptions import (
    InvalidPersistedPayloadError,
    InvalidRelationError,
    ObjectNotFoundError,
    ORKPError,
    RiskCompletenessError,
    SelfApprovalNotAllowedError,
)
from orkp.domain.risk_completeness import evaluate_risk_completeness
from orkp.domain.risk_evaluation import (
    calculate_risk_level,
    compare_initial_and_residual_risk,
)
from orkp.domain.risk_models import ResidualRiskEvaluationPayload


class RiskService:
    """Domain service for Risk Management objects."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def _rel(
        self, source_hex: str, target_hex: str, rel_type: str, created_by: str
    ) -> None:
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

    def create_object(
        self, object_type: str, payload: Dict[str, Any], owner_user_id: str
    ) -> RegulatoryObject:
        obj, _ = self.repo.create_object(
            object_type=object_type,
            payload=payload,
            owner_user_id=owner_user_id,
            created_by=owner_user_id,
        )
        self.repo.session.commit()
        return obj

    # ------------------------------------------------------------------
    # Atomic risk chain creation
    # ------------------------------------------------------------------

    def create_risk_chain(
        self,
        ra_hex: str,
        hz_hex: str,
        sq_hex: str,
        si_hex: str,
        hm_hex: str,
        actor: str,
    ) -> None:
        for name, h in [
            ("risk_analysis", ra_hex),
            ("hazard", hz_hex),
            ("sequence_of_events", sq_hex),
            ("hazardous_situation", si_hex),
            ("harm", hm_hex),
        ]:
            o = self.repo.get_by_uuid_hex(h)
            if o is None:
                raise ObjectNotFoundError(f"{name} {h} not found")
            if o.object_type != name:
                raise InvalidRelationError(f"Expected {name}, got {o.object_type}")
        self._rel(ra_hex, hz_hex, "has_hazard", actor)
        self._rel(hz_hex, sq_hex, "followed_by", actor)
        self._rel(sq_hex, si_hex, "creates_situation", actor)
        self._rel(si_hex, hm_hex, "may_cause", actor)
        self._rel(ra_hex, si_hex, "estimated_for", actor)
        self.repo.session.commit()

    def link_risk_to_product(self, ra_hex: str, prod_hex: str, actor: str) -> None:
        self._rel(ra_hex, prod_hex, "applies_to_product", actor)
        self.repo.session.commit()

    def add_risk_control(self, ra_hex: str, ctrl_hex: str, actor: str) -> None:
        self._rel(ra_hex, ctrl_hex, "controlled_by", actor)
        self.repo.session.commit()

    def link_control_verification(self, ev_hex: str, ctrl_hex: str, actor: str) -> None:
        self._rel(ev_hex, ctrl_hex, "verifies_control", actor)
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
        return calculate_risk_level(
            p.get("severity", "moderate"), p.get("probability", "possible")
        )

    def evaluate_residual_risk(
        self, ra_hex: str, rsev: str, rprob: str
    ) -> Dict[str, Any]:
        o = self.repo.get_by_uuid_hex(ra_hex)
        if o is None:
            raise ObjectNotFoundError(f"Risk analysis {ra_hex} not found")
        v = self.repo.get_version(o.object_uuid, o.current_version)
        p = v.payload_json if v else {}
        return compare_initial_and_residual_risk(
            p.get("severity", "moderate"),
            p.get("probability", "possible"),
            rsev,
            rprob,
        )

    # ------------------------------------------------------------------
    # Completeness traversal — current object versions only
    # ------------------------------------------------------------------

    def evaluate_risk_completeness(self, ra_hex: str) -> Dict[str, Any]:
        o = self.repo.get_by_uuid_hex(ra_hex)
        if o is None:
            raise ObjectNotFoundError(f"Risk analysis {ra_hex} not found")

        outgoing = self.repo.list_active_relations_for_source(o.object_uuid)
        incoming = self.repo.list_active_relations_for_target(o.object_uuid)
        current_outgoing = [
            relation
            for relation in outgoing
            if relation.source_version == o.current_version
        ]

        hazard_relations = [
            relation
            for relation in current_outgoing
            if relation.relation_type == "has_hazard"
        ]
        product_relations = [
            relation
            for relation in current_outgoing
            if relation.relation_type in {"applies_to_product", "applies_to_device"}
        ]
        control_relations = [
            relation
            for relation in current_outgoing
            if relation.relation_type == "controlled_by"
        ]

        has_hazard = bool(hazard_relations)
        has_product = bool(product_relations)
        has_controls = bool(control_relations)

        # Traverse the exact version-pinned hazard chain.
        has_sequence = has_situation = has_harm = False
        for hazard_relation in hazard_relations:
            hazard_outgoing = self.repo.list_active_relations_for_source(
                hazard_relation.target_uuid
            )
            for sequence_relation in hazard_outgoing:
                if (
                    sequence_relation.relation_type != "followed_by"
                    or sequence_relation.source_version
                    != hazard_relation.target_version
                ):
                    continue
                has_sequence = True
                sequence_outgoing = self.repo.list_active_relations_for_source(
                    sequence_relation.target_uuid
                )
                for situation_relation in sequence_outgoing:
                    if (
                        situation_relation.relation_type != "creates_situation"
                        or situation_relation.source_version
                        != sequence_relation.target_version
                    ):
                        continue
                    has_situation = True
                    situation_outgoing = self.repo.list_active_relations_for_source(
                        situation_relation.target_uuid
                    )
                    if any(
                        harm_relation.relation_type == "may_cause"
                        and harm_relation.source_version
                        == situation_relation.target_version
                        for harm_relation in situation_outgoing
                    ):
                        has_harm = True

        controls_verified = all(
            self._control_relation_is_verified(o, relation)
            for relation in control_relations
        )

        (
            has_residual,
            residual_acceptable,
            benefit_risk_approved,
        ) = self._current_residual_disposition(o, incoming)

        return evaluate_risk_completeness(
            ra_hex,
            has_hazard,
            has_sequence,
            has_situation,
            has_harm,
            has_product,
            has_controls,
            controls_verified,
            has_residual,
            residual_acceptable,
            benefit_risk_approved,
        )

    def _control_relation_is_verified(self, risk_analysis, control_relation) -> bool:
        """Require an eligible verification for the exact risk/control versions."""
        control = self.repo.get_by_uuid(control_relation.target_uuid)
        if control is None or control.object_type != "risk_control":
            return False
        control_version = self.repo.get_version(
            control.object_uuid, control_relation.target_version
        )
        if control_version is None:
            return False
        control_payload = control_version.payload_json or {}
        if not control_payload.get("verification_required", True):
            return True

        verification_service = ControlVerificationService(self.repo)
        incoming = self.repo.list_active_relations_for_target(control.object_uuid)
        for relation in incoming:
            if (
                relation.relation_type != "verifies_control"
                or relation.target_version != control_relation.target_version
            ):
                continue
            source = self.repo.get_by_uuid(relation.source_uuid)
            if (
                source is None
                or source.object_type != "control_verification"
                or source.current_version != relation.source_version
            ):
                continue
            try:
                verification = verification_service.get_verification(
                    source.uuid_hex, relation.source_version
                )
            except ORKPError:
                continue
            if not verification.eligible_for_residual_evaluation:
                continue
            payload = verification.payload
            if (
                payload.risk_analysis.object_uuid == risk_analysis.uuid_hex
                and payload.risk_analysis.object_version
                == risk_analysis.current_version
                and payload.risk_control.object_uuid == control.uuid_hex
                and payload.risk_control.object_version
                == control_relation.target_version
            ):
                return True
        return False

    def _current_residual_disposition(self, risk_analysis, incoming_relations):
        """Return disposition for the newest exact residual relation of this RA."""
        residual_relations = [
            relation
            for relation in incoming_relations
            if relation.relation_type == "residual_of"
            and relation.target_version == risk_analysis.current_version
        ]
        for relation in residual_relations:
            residual = self.repo.get_by_uuid(relation.source_uuid)
            if (
                residual is None
                or residual.object_type != "residual_risk_evaluation"
                or residual.current_version != relation.source_version
            ):
                continue
            residual_version = self.repo.get_version(
                residual.object_uuid, relation.source_version
            )
            if residual_version is None:
                continue
            try:
                payload = ResidualRiskEvaluationPayload(
                    **(residual_version.payload_json or {})
                )
            except ValidationError as exc:
                raise InvalidPersistedPayloadError(
                    "Stored residual risk evaluation payload is invalid"
                ) from exc
            if (
                payload.risk_analysis_uuid != risk_analysis.uuid_hex
                or payload.risk_analysis_version != risk_analysis.current_version
            ):
                raise InvalidRelationError(
                    "Residual risk relation and payload reference different risk-analysis versions"
                )
            benefit_risk_approved = False
            if not payload.acceptable:
                benefit_risk_approved = self._has_favorable_benefit_risk(
                    residual,
                    relation.source_version,
                    payload,
                )
            return True, payload.acceptable, benefit_risk_approved
        return False, False, False

    def _has_favorable_benefit_risk(
        self,
        residual,
        residual_version: int,
        residual_payload: ResidualRiskEvaluationPayload,
    ) -> bool:
        incoming = self.repo.list_active_relations_for_target(residual.object_uuid)
        for relation in incoming:
            if (
                relation.relation_type != "benefit_risk_for"
                or relation.target_version != residual_version
            ):
                continue
            analysis = self.repo.get_by_uuid(relation.source_uuid)
            if (
                analysis is None
                or analysis.object_type != "benefit_risk"
                or analysis.lifecycle_state not in {"approved", "effective"}
                or analysis.current_version != relation.source_version
            ):
                continue
            version = self.repo.get_version(
                analysis.object_uuid, relation.source_version
            )
            if version is None:
                continue
            try:
                payload = BenefitRiskAnalysisPayload(**(version.payload_json or {}))
            except ValidationError:
                continue
            if (
                payload.residual_evaluation.object_uuid == residual.uuid_hex
                and payload.residual_evaluation.object_version == residual_version
                and payload.risk_analysis.object_uuid
                == residual_payload.risk_analysis_uuid
                and payload.risk_analysis.object_version
                == residual_payload.risk_analysis_version
                and payload.risk_policy.object_uuid == residual_payload.risk_policy_uuid
                and payload.risk_policy.object_version
                == residual_payload.risk_policy_version
                and payload.conclusion == "favorable"
            ):
                return True
        return False

    def submit_for_review(self, ra_hex: str, actor: str) -> None:
        o = self.repo.get_by_uuid_hex(ra_hex)
        if o is None:
            raise ObjectNotFoundError(f"Risk analysis {ra_hex} not found")
        self.repo.transition_state(o.object_uuid, "in_review", actor)
        self.repo.session.commit()

    def approve_risk(
        self,
        ra_hex: str,
        approver: str,
        created_by: str,
        comments: Optional[str] = None,
    ) -> None:
        o = self.repo.get_by_uuid_hex(ra_hex)
        if o is None:
            raise ObjectNotFoundError(f"Risk analysis {ra_hex} not found")
        if o.owner_user_id == approver:
            raise SelfApprovalNotAllowedError("Risk author cannot approve own analysis")
        c = self.evaluate_risk_completeness(ra_hex)
        if not c["complete"]:
            raise RiskCompletenessError(
                "Risk approval blocked: " + "; ".join(c["blocking_issues"])
            )
        self.repo.transition_state(o.object_uuid, "approved", approver, comments)
        self.repo.session.commit()

    def reject_risk(self, ra_hex: str, reviewer: str, comments: str) -> None:
        o = self.repo.get_by_uuid_hex(ra_hex)
        if o is None:
            raise ObjectNotFoundError(f"Risk analysis {ra_hex} not found")
        self.repo.transition_state(o.object_uuid, "rejected", reviewer, comments)
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
                (self.repo.list_all_relations_for_source(node_uuid), "outgoing"),
                (self.repo.list_all_relations_for_target(node_uuid), "incoming"),
            ]:
                for r in rels:
                    src = _bin_to_str(r.source_uuid)
                    tgt = _bin_to_str(r.target_uuid)
                    src_o = self.repo.get_by_uuid(r.source_uuid)
                    tgt_o = self.repo.get_by_uuid(r.target_uuid)
                    edges.append(
                        {
                            "relation_uuid": _bin_to_str(r.relation_uuid),
                            "relation_type": r.relation_type,
                            "lifecycle_state": r.lifecycle_state,
                            "source_uuid": src,
                            "source_version": r.source_version,
                            "source_object_type": src_o.object_type
                            if src_o
                            else "unknown",
                            "target_uuid": tgt,
                            "target_version": r.target_version,
                            "target_object_type": tgt_o.object_type
                            if tgt_o
                            else "unknown",
                            "direction": direction,
                        }
                    )
                    if direction == "outgoing":
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
            if r.relation_type in (
                "controlled_by",
                "estimated_for",
                "applies_to_product",
                "has_hazard",
                "followed_by",
                "creates_situation",
                "may_cause",
            ):
                t = self.repo.get_by_uuid(r.target_uuid)
                if t:
                    affected.append(
                        {
                            "risk_uuid": t.uuid_hex,
                            "risk_type": t.object_type,
                            "relation_type": r.relation_type,
                        }
                    )
        return {
            "changed_object_uuid": obj_hex,
            "affected_risk_count": len(affected),
            "affected_risks": affected,
            "rule_codes": ["RISK-IMPACT-CHANGE-001"] if affected else [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

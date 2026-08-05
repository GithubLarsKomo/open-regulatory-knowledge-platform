"""Product-level Overall Residual Risk evaluation service."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.benefit_risk_models import BenefitRiskAnalysisPayload
from orkp.domain.exceptions import (
    InvalidObjectIdentifierError,
    InvalidPersistedPayloadError,
    InvalidRelationError,
    ObjectNotFoundError,
    RiskEvaluationError,
    SelfApprovalNotAllowedError,
)
from orkp.domain.overall_residual_risk_models import (
    OverallResidualRiskCreateRequest,
    OverallResidualRiskEntry,
    OverallResidualRiskPayload,
    OverallResidualRiskResponse,
)
from orkp.domain.risk_models import ResidualRiskEvaluationPayload, RiskPolicyPayload
from orkp.domain.versioned_loader import load_versioned_object


class OverallResidualRiskService:
    """Aggregate all current approved/effective Product risks deterministically."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_evaluation(
        self,
        product_hex: str,
        request: OverallResidualRiskCreateRequest,
    ) -> OverallResidualRiskResponse:
        product = load_versioned_object(
            self.repo,
            product_hex,
            request.product.object_version,
            "product",
        )
        if product.object.uuid_hex != request.product.object_uuid:
            raise InvalidRelationError("Path Product UUID does not match request reference")
        if product.object.current_version != request.product.object_version:
            raise InvalidRelationError(
                "Overall Residual Risk must reference the current Product version"
            )

        risks = self._collect_current_product_risks(product.object)
        if not risks:
            raise RiskEvaluationError(
                "Overall Residual Risk requires at least one current approved/effective "
                "Risk Analysis linked to the Product"
            )

        entries = [self._build_entry(risk) for risk in risks]
        entries.sort(
            key=lambda entry: (
                entry.risk_analysis.object_uuid,
                entry.risk_analysis.object_version,
            )
        )

        payload = OverallResidualRiskPayload(
            **request.model_dump(),
            evaluation_id=f"orr-{uuid4().hex[:12]}",
            entries=entries,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            evaluation, _ = self.repo.create_object(
                object_type="overall_residual_risk",
                payload=payload.model_dump(),
                owner_user_id=request.evaluator_user_id,
                created_by=request.evaluator_user_id,
            )
            version = evaluation.current_version
            self.repo.create_relation(
                source_uuid=evaluation.object_uuid,
                source_version=version,
                target_uuid=product.object.object_uuid,
                target_version=request.product.object_version,
                relation_type="overall_risk_for",
                created_by=request.evaluator_user_id,
            )

            seen_policies: set[tuple[str, int]] = set()
            for entry in entries:
                residual = self.repo.get_by_uuid_hex(
                    entry.residual_evaluation.object_uuid
                )
                if residual is None:
                    raise ObjectNotFoundError(
                        f"Residual Risk Evaluation "
                        f"{entry.residual_evaluation.object_uuid} not found"
                    )
                self.repo.create_relation(
                    source_uuid=evaluation.object_uuid,
                    source_version=version,
                    target_uuid=residual.object_uuid,
                    target_version=entry.residual_evaluation.object_version,
                    relation_type="aggregates_residual_risk",
                    created_by=request.evaluator_user_id,
                )

                policy_key = (
                    entry.risk_policy.object_uuid,
                    entry.risk_policy.object_version,
                )
                if policy_key not in seen_policies:
                    policy = self.repo.get_by_uuid_hex(entry.risk_policy.object_uuid)
                    if policy is None:
                        raise ObjectNotFoundError(
                            f"Risk Policy {entry.risk_policy.object_uuid} not found"
                        )
                    self.repo.create_relation(
                        source_uuid=evaluation.object_uuid,
                        source_version=version,
                        target_uuid=policy.object_uuid,
                        target_version=entry.risk_policy.object_version,
                        relation_type="uses_risk_policy",
                        created_by=request.evaluator_user_id,
                    )
                    seen_policies.add(policy_key)

                for benefit_reference in entry.benefit_risk_analyses:
                    benefit = self.repo.get_by_uuid_hex(benefit_reference.object_uuid)
                    if benefit is None:
                        raise ObjectNotFoundError(
                            f"Benefit-Risk Analysis "
                            f"{benefit_reference.object_uuid} not found"
                        )
                    self.repo.create_relation(
                        source_uuid=evaluation.object_uuid,
                        source_version=version,
                        target_uuid=benefit.object_uuid,
                        target_version=benefit_reference.object_version,
                        relation_type="considers_benefit_risk",
                        created_by=request.evaluator_user_id,
                    )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return OverallResidualRiskResponse(
            object_uuid=evaluation.uuid_hex,
            object_version=version,
            lifecycle_state=evaluation.lifecycle_state,
            payload=payload,
        )

    def transition_state(
        self,
        evaluation_hex: str,
        new_state: str,
        actor_user_id: str,
        comments: str | None = None,
    ) -> OverallResidualRiskResponse:
        current_version = self._current_version(evaluation_hex)
        loaded = load_versioned_object(
            self.repo,
            evaluation_hex,
            current_version,
            "overall_residual_risk",
        )
        if new_state == "approved" and actor_user_id == loaded.object.owner_user_id:
            raise SelfApprovalNotAllowedError(
                "Overall Residual Risk evaluation must be approved by another user"
            )
        try:
            self.repo.transition_state(
                loaded.object.object_uuid,
                new_state,
                actor_user_id,
                comments=comments,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise
        return self.get_evaluation(loaded.object.uuid_hex, loaded.object.current_version)

    def get_evaluation(
        self,
        evaluation_hex: str,
        version: int,
    ) -> OverallResidualRiskResponse:
        loaded = load_versioned_object(
            self.repo,
            evaluation_hex,
            version,
            "overall_residual_risk",
        )
        try:
            payload = OverallResidualRiskPayload(**loaded.payload)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Stored Overall Residual Risk payload is invalid"
            ) from exc
        return OverallResidualRiskResponse(
            object_uuid=loaded.object.uuid_hex,
            object_version=version,
            lifecycle_state=loaded.object.lifecycle_state,
            payload=payload,
        )

    def _collect_current_product_risks(self, product) -> list:
        found = {}

        for relation in self.repo.list_active_relations_for_source(
            product.object_uuid
        ):
            if (
                relation.relation_type != "has_risk"
                or relation.source_version != product.current_version
            ):
                continue
            self._add_current_approved_risk(
                found,
                relation.target_uuid,
                relation.target_version,
            )

        for relation in self.repo.list_active_relations_for_target(
            product.object_uuid
        ):
            if (
                relation.relation_type != "applies_to_product"
                or relation.target_version != product.current_version
            ):
                continue
            self._add_current_approved_risk(
                found,
                relation.source_uuid,
                relation.source_version,
            )

        return [found[key] for key in sorted(found)]

    def _add_current_approved_risk(
        self,
        found: dict,
        risk_uuid: bytes,
        risk_version: int,
    ) -> None:
        risk = self.repo.get_by_uuid(risk_uuid)
        if (
            risk is None
            or risk.object_type != "risk_analysis"
            or risk.lifecycle_state not in {"approved", "effective"}
            or risk.current_version != risk_version
        ):
            return
        found[(risk.uuid_hex, risk_version)] = risk

    def _build_entry(self, risk) -> OverallResidualRiskEntry:
        residual, residual_payload = self._load_unique_current_residual(risk)
        policy = load_versioned_object(
            self.repo,
            residual_payload.risk_policy_uuid,
            residual_payload.risk_policy_version,
            "risk_policy",
        )
        try:
            RiskPolicyPayload(**policy.payload)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                f"Risk Policy {residual_payload.risk_policy_uuid} payload is invalid"
            ) from exc

        benefit_references = []
        if not residual_payload.acceptable:
            benefit_references = self._load_favorable_benefit_risks(
                residual,
                residual.current_version,
                residual_payload,
            )
            if not benefit_references:
                raise RiskEvaluationError(
                    f"Risk Analysis {risk.uuid_hex} has unacceptable residual risk "
                    "without an approved/effective favorable Benefit-Risk Analysis"
                )

        return OverallResidualRiskEntry(
            risk_analysis={
                "object_uuid": risk.uuid_hex,
                "object_version": risk.current_version,
            },
            residual_evaluation={
                "object_uuid": residual.uuid_hex,
                "object_version": residual.current_version,
            },
            risk_policy={
                "object_uuid": policy.object.uuid_hex,
                "object_version": residual_payload.risk_policy_version,
            },
            residual_acceptable=residual_payload.acceptable,
            benefit_risk_analyses=benefit_references,
        )

    def _load_unique_current_residual(self, risk):
        candidates = []
        for relation in self.repo.list_active_relations_for_target(risk.object_uuid):
            if (
                relation.relation_type != "residual_of"
                or relation.target_version != risk.current_version
            ):
                continue
            residual = self.repo.get_by_uuid(relation.source_uuid)
            if (
                residual is None
                or residual.object_type != "residual_risk_evaluation"
                or residual.current_version != relation.source_version
            ):
                continue
            version = self.repo.get_version(
                residual.object_uuid,
                relation.source_version,
            )
            if version is None:
                continue
            try:
                payload = ResidualRiskEvaluationPayload(**(version.payload_json or {}))
            except ValidationError as exc:
                raise InvalidPersistedPayloadError(
                    f"Residual Risk Evaluation {residual.uuid_hex} payload is invalid"
                ) from exc
            if (
                payload.risk_analysis_uuid != risk.uuid_hex
                or payload.risk_analysis_version != risk.current_version
            ):
                raise InvalidRelationError(
                    "Residual Risk relation and payload reference different "
                    "Risk Analysis versions"
                )
            candidates.append((residual, payload))

        if not candidates:
            raise RiskEvaluationError(
                f"Risk Analysis {risk.uuid_hex} has no current Residual Risk Evaluation"
            )
        if len(candidates) > 1:
            raise InvalidRelationError(
                f"Risk Analysis {risk.uuid_hex} has multiple current Residual Risk "
                "Evaluations; overall aggregation is ambiguous"
            )
        return candidates[0]

    def _load_favorable_benefit_risks(
        self,
        residual,
        residual_version: int,
        residual_payload: ResidualRiskEvaluationPayload,
    ) -> list[dict]:
        references = []
        for relation in self.repo.list_active_relations_for_target(
            residual.object_uuid
        ):
            if (
                relation.relation_type != "benefit_risk_for"
                or relation.target_version != residual_version
            ):
                continue
            benefit = self.repo.get_by_uuid(relation.source_uuid)
            if (
                benefit is None
                or benefit.object_type != "benefit_risk"
                or benefit.lifecycle_state not in {"approved", "effective"}
                or benefit.current_version != relation.source_version
            ):
                continue
            version = self.repo.get_version(
                benefit.object_uuid,
                relation.source_version,
            )
            if version is None:
                continue
            try:
                payload = BenefitRiskAnalysisPayload(**(version.payload_json or {}))
            except ValidationError:
                continue
            if (
                payload.residual_evaluation.object_uuid != residual.uuid_hex
                or payload.residual_evaluation.object_version != residual_version
                or payload.risk_analysis.object_uuid
                != residual_payload.risk_analysis_uuid
                or payload.risk_analysis.object_version
                != residual_payload.risk_analysis_version
                or payload.risk_policy.object_uuid != residual_payload.risk_policy_uuid
                or payload.risk_policy.object_version
                != residual_payload.risk_policy_version
                or payload.conclusion != "favorable"
            ):
                continue
            references.append(
                {
                    "object_uuid": benefit.uuid_hex,
                    "object_version": relation.source_version,
                }
            )
        references.sort(key=lambda reference: (reference["object_uuid"], reference["object_version"]))
        return references

    def _current_version(self, evaluation_hex: str) -> int:
        try:
            normalized = UUID(evaluation_hex).hex
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidObjectIdentifierError(
                f"Invalid UUID format: {evaluation_hex}"
            ) from exc
        obj = self.repo.get_by_uuid_hex(normalized)
        if obj is None:
            raise ObjectNotFoundError(
                f"Overall Residual Risk evaluation {normalized} not found"
            )
        return obj.current_version

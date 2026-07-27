"""Version-pinned risk-control verification service."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    InvalidLifecycleStateError,
    InvalidPersistedPayloadError,
    InvalidRelationError,
    RiskControlVerificationError,
)
from orkp.domain.risk_models import (
    ControlVerificationCreateRequest,
    ControlVerificationPayload,
    ControlVerificationResponse,
    InitialRiskEvaluationPayload,
)
from orkp.domain.versioned_loader import load_versioned_object


class ControlVerificationService:
    """Create and read immutable, version-pinned control verifications."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_verification(
        self,
        risk_control_hex: str,
        request: ControlVerificationCreateRequest,
    ) -> ControlVerificationResponse:
        risk_control_hex = UUID(risk_control_hex).hex
        if request.risk_control.object_uuid != risk_control_hex:
            raise InvalidRelationError(
                "Path risk control UUID does not match request risk_control reference"
            )

        risk_analysis = load_versioned_object(
            self.repo,
            request.risk_analysis.object_uuid,
            request.risk_analysis.object_version,
            "risk_analysis",
        )
        risk_control = load_versioned_object(
            self.repo,
            request.risk_control.object_uuid,
            request.risk_control.object_version,
            "risk_control",
        )
        initial_evaluation = load_versioned_object(
            self.repo,
            request.initial_evaluation.object_uuid,
            request.initial_evaluation.object_version,
            "initial_risk_evaluation",
        )
        risk_policy = load_versioned_object(
            self.repo,
            request.risk_policy.object_uuid,
            request.risk_policy.object_version,
            "risk_policy",
        )

        if risk_control.object.lifecycle_state in {"obsolete", "deleted"}:
            raise InvalidLifecycleStateError(
                "Obsolete or deleted risk controls cannot be verified"
            )
        if risk_policy.object.lifecycle_state not in {"approved", "effective"}:
            raise InvalidLifecycleStateError(
                "Risk policy must be approved or effective"
            )

        try:
            initial_payload = InitialRiskEvaluationPayload(**initial_evaluation.payload)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Stored initial risk evaluation payload is invalid"
            ) from exc

        if (
            initial_payload.risk_analysis_uuid
            != request.risk_analysis.object_uuid
            or initial_payload.risk_analysis_version
            != request.risk_analysis.object_version
        ):
            raise InvalidRelationError(
                "Initial evaluation does not reference the selected risk analysis version"
            )
        if (
            initial_payload.risk_policy_uuid != request.risk_policy.object_uuid
            or initial_payload.risk_policy_version != request.risk_policy.object_version
        ):
            raise InvalidRelationError(
                "Initial evaluation does not reference the selected risk policy version"
            )

        controlled_by = [
            relation
            for relation in self.repo.list_active_relations_for_source(
                risk_analysis.object.object_uuid
            )
            if relation.relation_type == "controlled_by"
            and relation.source_version == request.risk_analysis.object_version
            and relation.target_uuid == risk_control.object.object_uuid
            and relation.target_version == request.risk_control.object_version
        ]
        if not controlled_by:
            raise InvalidRelationError(
                "Risk control is not linked to the selected risk analysis version"
            )

        evidence_objects = []
        for evidence_ref in request.evidence:
            evidence = load_versioned_object(
                self.repo,
                evidence_ref.object_uuid,
                evidence_ref.object_version,
                "evidence",
            )
            if evidence.object.lifecycle_state not in {"approved", "effective"}:
                raise InvalidLifecycleStateError(
                    "Verification evidence must be approved or effective"
                )
            evidence_objects.append((evidence_ref, evidence))

        payload = ControlVerificationPayload(
            **request.model_dump(),
            verification_id=f"cv-{uuid4().hex[:12]}",
            verified_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            verification, _ = self.repo.create_object(
                object_type="control_verification",
                payload=payload.model_dump(),
                owner_user_id=request.verified_by_user_id,
                created_by=request.verified_by_user_id,
            )
            verification_version = verification.current_version
            self.repo.create_relation(
                source_uuid=verification.object_uuid,
                source_version=verification_version,
                target_uuid=risk_control.object.object_uuid,
                target_version=request.risk_control.object_version,
                relation_type="verifies_control",
                created_by=request.verified_by_user_id,
            )
            self.repo.create_relation(
                source_uuid=verification.object_uuid,
                source_version=verification_version,
                target_uuid=risk_analysis.object.object_uuid,
                target_version=request.risk_analysis.object_version,
                relation_type="derived_from",
                created_by=request.verified_by_user_id,
                properties={"role": "verifies_control_for"},
            )
            self.repo.create_relation(
                source_uuid=verification.object_uuid,
                source_version=verification_version,
                target_uuid=initial_evaluation.object.object_uuid,
                target_version=request.initial_evaluation.object_version,
                relation_type="derived_from_initial_evaluation",
                created_by=request.verified_by_user_id,
            )
            self.repo.create_relation(
                source_uuid=verification.object_uuid,
                source_version=verification_version,
                target_uuid=risk_policy.object.object_uuid,
                target_version=request.risk_policy.object_version,
                relation_type="uses_risk_policy",
                created_by=request.verified_by_user_id,
            )
            for evidence_ref, evidence in evidence_objects:
                self.repo.create_relation(
                    source_uuid=evidence.object.object_uuid,
                    source_version=evidence_ref.object_version,
                    target_uuid=verification.object_uuid,
                    target_version=verification_version,
                    relation_type="supports_verification",
                    created_by=request.verified_by_user_id,
                )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return self._response(verification.uuid_hex, verification_version)

    def get_verification(self, verification_hex: str, version: int) -> ControlVerificationResponse:
        return self._response(UUID(verification_hex).hex, version)

    def list_for_risk_control(self, risk_control_hex: str) -> list[ControlVerificationResponse]:
        control = load_versioned_object(
            self.repo,
            UUID(risk_control_hex).hex,
            self.repo.get_by_uuid_hex(UUID(risk_control_hex).hex).current_version,
            "risk_control",
        )
        responses = []
        for relation in self.repo.list_active_relations_for_target(control.object.object_uuid):
            if relation.relation_type != "verifies_control":
                continue
            responses.append(
                self._response(UUID(bytes=relation.source_uuid).hex, relation.source_version)
            )
        return responses

    def evaluate_eligibility(self, lifecycle_state: str, payload: ControlVerificationPayload) -> bool:
        return (
            lifecycle_state == "effective"
            and payload.conclusion in {"passed", "passed_with_limitations"}
            and payload.implementation_verified
            and payload.effectiveness_verified
            and payload.no_new_uncontrolled_risks
            and payload.effectiveness_result == "effective"
        )

    def _response(self, verification_hex: str, version: int) -> ControlVerificationResponse:
        loaded = load_versioned_object(
            self.repo,
            verification_hex,
            version,
            "control_verification",
        )
        try:
            payload = ControlVerificationPayload(**loaded.payload)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Stored control verification payload is invalid"
            ) from exc
        return ControlVerificationResponse(
            object_uuid=loaded.object.uuid_hex,
            object_version=version,
            lifecycle_state=loaded.object.lifecycle_state,
            eligible_for_residual_evaluation=self.evaluate_eligibility(
                loaded.object.lifecycle_state, payload
            ),
            payload=payload,
        )

    def assert_eligible_for_residual(
        self,
        verification_hex: str,
        version: int,
        risk_analysis_hex: str,
        risk_analysis_version: int,
        initial_evaluation_hex: str,
        initial_evaluation_version: int,
        risk_policy_hex: str,
        risk_policy_version: int,
    ) -> ControlVerificationResponse:
        response = self.get_verification(verification_hex, version)
        if not response.eligible_for_residual_evaluation:
            raise RiskControlVerificationError(
                "Control verification is not effective and eligible"
            )
        payload = response.payload
        expected = (
            (payload.risk_analysis.object_uuid, payload.risk_analysis.object_version),
            (payload.initial_evaluation.object_uuid, payload.initial_evaluation.object_version),
            (payload.risk_policy.object_uuid, payload.risk_policy.object_version),
        )
        actual = (
            (risk_analysis_hex, risk_analysis_version),
            (initial_evaluation_hex, initial_evaluation_version),
            (risk_policy_hex, risk_policy_version),
        )
        if expected != actual:
            raise InvalidRelationError(
                "Control verification references a different risk context"
            )
        return response

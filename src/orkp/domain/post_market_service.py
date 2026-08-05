"""Post-market safety information and Risk Impact Assessment service."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    InvalidObjectIdentifierError,
    InvalidPersistedPayloadError,
    InvalidRelationError,
    ObjectNotFoundError,
    SelfApprovalNotAllowedError,
)
from orkp.domain.post_market_models import (
    PostMarketInformationCreateRequest,
    PostMarketInformationPayload,
    PostMarketInformationResponse,
    PostMarketIngestionResponse,
    RiskImpactAssessmentCompleteRequest,
    RiskImpactAssessmentDraftPayload,
    RiskImpactAssessmentResponse,
)
from orkp.domain.versioned_loader import load_versioned_object


class PostMarketRiskService:
    """Create safety information and enforce auditable Risk Impact Assessment."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def ingest_information(
        self,
        risk_analysis_hex: str,
        request: PostMarketInformationCreateRequest,
    ) -> PostMarketIngestionResponse:
        risk = load_versioned_object(
            self.repo,
            risk_analysis_hex,
            request.risk_analysis.object_version,
            "risk_analysis",
        )
        if risk.object.uuid_hex != request.risk_analysis.object_uuid:
            raise InvalidRelationError(
                "Path Risk Analysis UUID does not match request reference"
            )
        if risk.object.current_version != request.risk_analysis.object_version:
            raise InvalidRelationError(
                "Post-market information must reference the current Risk Analysis version"
            )

        information_payload = PostMarketInformationPayload(
            **request.model_dump(),
            information_id=f"pmi-{uuid4().hex[:12]}",
            received_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            information, _ = self.repo.create_object(
                "post_market_information",
                information_payload.model_dump(),
                request.reported_by_user_id,
                request.reported_by_user_id,
            )
            information_version = information.current_version
            assessment_payload = RiskImpactAssessmentDraftPayload(
                assessment_id=f"ria-{uuid4().hex[:12]}",
                risk_analysis=request.risk_analysis,
                post_market_information={
                    "object_uuid": information.uuid_hex,
                    "object_version": information_version,
                },
            )
            assessment, _ = self.repo.create_object(
                "risk_impact_assessment",
                assessment_payload.model_dump(),
                request.reported_by_user_id,
                request.reported_by_user_id,
            )
            assessment_version = assessment.current_version

            self.repo.create_relation(
                source_uuid=information.object_uuid,
                source_version=information_version,
                target_uuid=risk.object.object_uuid,
                target_version=request.risk_analysis.object_version,
                relation_type="impacts_risk",
                created_by=request.reported_by_user_id,
            )
            self.repo.create_relation(
                source_uuid=risk.object.object_uuid,
                source_version=request.risk_analysis.object_version,
                target_uuid=information.object_uuid,
                target_version=information_version,
                relation_type="informed_by",
                created_by=request.reported_by_user_id,
            )
            self._create_assessment_provenance(
                assessment.object_uuid,
                assessment_version,
                risk.object.object_uuid,
                request.risk_analysis.object_version,
                information.object_uuid,
                information_version,
                request.reported_by_user_id,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return PostMarketIngestionResponse(
            information=PostMarketInformationResponse(
                object_uuid=information.uuid_hex,
                object_version=information_version,
                lifecycle_state=information.lifecycle_state,
                payload=information_payload,
            ),
            impact_assessment=RiskImpactAssessmentResponse(
                object_uuid=assessment.uuid_hex,
                object_version=assessment_version,
                lifecycle_state=assessment.lifecycle_state,
                payload=assessment_payload,
            ),
        )

    def complete_assessment(
        self,
        assessment_hex: str,
        request: RiskImpactAssessmentCompleteRequest,
    ) -> RiskImpactAssessmentResponse:
        assessment = self._load_current_assessment(assessment_hex)
        if assessment.object.lifecycle_state != "draft":
            raise InvalidRelationError(
                "Risk Impact Assessment can only be completed while in draft"
            )
        current_payload = self._parse_assessment_payload(assessment.payload)
        if current_payload.outcome != "pending":
            raise InvalidRelationError("Risk Impact Assessment is already completed")
        self._assert_current_context(
            assessment.object.object_uuid,
            assessment.version.version_no,
            current_payload,
        )

        completed_payload = RiskImpactAssessmentDraftPayload(
            assessment_id=current_payload.assessment_id,
            risk_analysis=current_payload.risk_analysis,
            post_market_information=current_payload.post_market_information,
            outcome=request.outcome,
            rationale=request.rationale,
            requires_risk_review=request.requires_risk_review,
            assessor_user_id=request.assessor_user_id,
            assessed_at=datetime.now(timezone.utc).isoformat(),
        )

        risk_uuid = UUID(hex=current_payload.risk_analysis.object_uuid).bytes
        information_uuid = UUID(
            hex=current_payload.post_market_information.object_uuid
        ).bytes
        try:
            version = self.repo.create_version(
                assessment.object.object_uuid,
                completed_payload.model_dump(),
                request.assessor_user_id,
            )
            self._create_assessment_provenance(
                assessment.object.object_uuid,
                version.version_no,
                risk_uuid,
                current_payload.risk_analysis.object_version,
                information_uuid,
                current_payload.post_market_information.object_version,
                request.assessor_user_id,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return self.get_assessment(assessment.object.uuid_hex, version.version_no)

    def transition_assessment(
        self,
        assessment_hex: str,
        new_state: str,
        actor_user_id: str,
        comments: str | None = None,
    ) -> RiskImpactAssessmentResponse:
        assessment = self._load_current_assessment(assessment_hex)
        payload = self._parse_assessment_payload(assessment.payload)

        if new_state == "in_review" and payload.outcome == "pending":
            raise InvalidRelationError(
                "Pending Risk Impact Assessment must be completed before review"
            )
        if new_state == "approved":
            if payload.outcome == "pending" or payload.assessor_user_id is None:
                raise InvalidRelationError(
                    "Pending Risk Impact Assessment cannot be approved"
                )
            if actor_user_id == payload.assessor_user_id:
                raise SelfApprovalNotAllowedError(
                    "Risk Impact assessor cannot approve their own assessment"
                )
            self._assert_current_context(
                assessment.object.object_uuid,
                assessment.version.version_no,
                payload,
            )

        try:
            self.repo.transition_state(
                assessment.object.object_uuid,
                new_state,
                actor_user_id,
                comments=comments,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return self.get_assessment(
            assessment.object.uuid_hex,
            assessment.object.current_version,
        )

    def get_information(
        self,
        information_hex: str,
        version: int,
    ) -> PostMarketInformationResponse:
        loaded = load_versioned_object(
            self.repo,
            information_hex,
            version,
            "post_market_information",
        )
        payload = self._parse_information_payload(loaded.payload)
        return PostMarketInformationResponse(
            object_uuid=loaded.object.uuid_hex,
            object_version=version,
            lifecycle_state=loaded.object.lifecycle_state,
            payload=payload,
        )

    def get_assessment(
        self,
        assessment_hex: str,
        version: int,
    ) -> RiskImpactAssessmentResponse:
        loaded = load_versioned_object(
            self.repo,
            assessment_hex,
            version,
            "risk_impact_assessment",
        )
        payload = self._parse_assessment_payload(loaded.payload)
        return RiskImpactAssessmentResponse(
            object_uuid=loaded.object.uuid_hex,
            object_version=version,
            lifecycle_state=loaded.object.lifecycle_state,
            payload=payload,
        )

    def _load_current_assessment(self, assessment_hex: str):
        try:
            normalized = UUID(assessment_hex).hex
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidObjectIdentifierError(
                f"Invalid UUID format: {assessment_hex}"
            ) from exc
        obj = self.repo.get_by_uuid_hex(normalized)
        if obj is None:
            raise ObjectNotFoundError(
                f"Risk Impact Assessment {normalized} not found"
            )
        return load_versioned_object(
            self.repo,
            normalized,
            obj.current_version,
            "risk_impact_assessment",
        )

    def _parse_information_payload(self, data: dict) -> PostMarketInformationPayload:
        try:
            return PostMarketInformationPayload(**data)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Stored post-market information payload is invalid"
            ) from exc

    def _parse_assessment_payload(self, data: dict) -> RiskImpactAssessmentDraftPayload:
        try:
            return RiskImpactAssessmentDraftPayload(**data)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Stored Risk Impact Assessment payload is invalid"
            ) from exc

    def _assert_current_context(
        self,
        assessment_uuid: bytes,
        assessment_version: int,
        payload: RiskImpactAssessmentDraftPayload,
    ) -> None:
        risk = load_versioned_object(
            self.repo,
            payload.risk_analysis.object_uuid,
            payload.risk_analysis.object_version,
            "risk_analysis",
        )
        if risk.object.current_version != payload.risk_analysis.object_version:
            raise InvalidRelationError(
                "Risk Analysis changed after Risk Impact Assessment was created"
            )
        information = load_versioned_object(
            self.repo,
            payload.post_market_information.object_uuid,
            payload.post_market_information.object_version,
            "post_market_information",
        )
        if (
            information.object.current_version
            != payload.post_market_information.object_version
        ):
            raise InvalidRelationError(
                "Post-market information changed after Risk Impact Assessment was created"
            )
        information_payload = self._parse_information_payload(information.payload)
        if information_payload.risk_analysis != payload.risk_analysis:
            raise InvalidRelationError(
                "Post-market information and Risk Impact Assessment reference different Risk Analysis versions"
            )

        risk_uuid = risk.object.object_uuid
        information_uuid = information.object.object_uuid
        self._require_exact_relation(
            information_uuid,
            payload.post_market_information.object_version,
            "impacts_risk",
            risk_uuid,
            payload.risk_analysis.object_version,
        )
        self._require_exact_relation(
            risk_uuid,
            payload.risk_analysis.object_version,
            "informed_by",
            information_uuid,
            payload.post_market_information.object_version,
        )
        self._require_exact_relation(
            assessment_uuid,
            assessment_version,
            "derived_from",
            information_uuid,
            payload.post_market_information.object_version,
            role="impact_assessment_source",
        )
        self._require_exact_relation(
            assessment_uuid,
            assessment_version,
            "derived_from",
            risk_uuid,
            payload.risk_analysis.object_version,
            role="assessed_risk",
        )

    def _create_assessment_provenance(
        self,
        assessment_uuid: bytes,
        assessment_version: int,
        risk_uuid: bytes,
        risk_version: int,
        information_uuid: bytes,
        information_version: int,
        created_by: str,
    ) -> None:
        self.repo.create_relation(
            source_uuid=assessment_uuid,
            source_version=assessment_version,
            target_uuid=information_uuid,
            target_version=information_version,
            relation_type="derived_from",
            created_by=created_by,
            properties={"role": "impact_assessment_source"},
        )
        self.repo.create_relation(
            source_uuid=assessment_uuid,
            source_version=assessment_version,
            target_uuid=risk_uuid,
            target_version=risk_version,
            relation_type="derived_from",
            created_by=created_by,
            properties={"role": "assessed_risk"},
        )

    def _require_exact_relation(
        self,
        source_uuid: bytes,
        source_version: int,
        relation_type: str,
        target_uuid: bytes,
        target_version: int,
        *,
        role: str | None = None,
    ) -> None:
        for relation in self.repo.list_active_relations_for_source(source_uuid):
            if (
                relation.relation_type == relation_type
                and relation.source_version == source_version
                and relation.target_uuid == target_uuid
                and relation.target_version == target_version
                and (
                    role is None
                    or (
                        relation.properties is not None
                        and relation.properties.get("role") == role
                    )
                )
            ):
                return
        role_suffix = f" with role '{role}'" if role else ""
        raise InvalidRelationError(
            f"Missing exact {relation_type}{role_suffix} provenance relation"
        )

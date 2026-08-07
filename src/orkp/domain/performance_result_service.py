"""Performance Result evidence service."""

from pydantic import ValidationError

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    InvalidPersistedPayloadError,
    InvalidRelationError,
)
from orkp.domain.performance_models import PerformanceStudyPayload
from orkp.domain.performance_result_models import (
    PERFORMANCE_EVIDENCE_TYPES,
    PerformanceResultCreateRequest,
    PerformanceResultPayload,
    PerformanceResultResponse,
)
from orkp.domain.versioned_loader import load_versioned_object


_SOURCE_ROLE = {
    "source_data": "statistical_source_data",
    "validated_report": "validated_study_report",
}
_VALIDATED_REPORT_TYPES = {"internal_report", "external_report"}


class PerformanceResultService:
    """Create and read version-pinned Performance Result evidence."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_result(
        self,
        study_hex: str,
        request: PerformanceResultCreateRequest,
    ) -> PerformanceResultResponse:
        study = load_versioned_object(
            self.repo,
            study_hex,
            request.study.object_version,
            "study",
        )
        if study.object.uuid_hex != request.study.object_uuid:
            raise InvalidRelationError(
                "Path Study UUID does not match request reference"
            )
        if study.object.current_version != request.study.object_version:
            raise InvalidRelationError(
                "Performance Result must reference the current Study version"
            )
        try:
            study_payload = PerformanceStudyPayload(**study.payload)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Stored Performance Study payload is invalid"
            ) from exc

        claims = []
        for reference in request.claims:
            claim = load_versioned_object(
                self.repo,
                reference.object_uuid,
                reference.object_version,
                "claim",
            )
            if claim.object.current_version != reference.object_version:
                raise InvalidRelationError(
                    "Performance Result must reference current Claim versions"
                )
            claims.append(claim)

        statistical_sources = []
        for source_reference in request.statistical_sources:
            source = load_versioned_object(
                self.repo,
                source_reference.evidence.object_uuid,
                source_reference.evidence.object_version,
                "evidence",
            )
            if (
                source.object.current_version
                != source_reference.evidence.object_version
            ):
                raise InvalidRelationError(
                    "Performance Result must reference current statistical source versions"
                )

            evidence_type = (source.payload or {}).get("evidence_type")
            if source_reference.source_kind == "source_data":
                if evidence_type != "internal_document":
                    raise InvalidRelationError(
                        "source_data must reference internal_document Evidence"
                    )
            else:
                if evidence_type not in _VALIDATED_REPORT_TYPES:
                    raise InvalidRelationError(
                        "validated_report must reference internal_report or external_report Evidence"
                    )
                if source.object.lifecycle_state not in {"approved", "effective"}:
                    raise InvalidRelationError(
                        "validated_report Evidence must be approved or effective"
                    )
                if source.version.status != "approved":
                    raise InvalidRelationError(
                        "validated_report must reference an approved Evidence version"
                    )
            statistical_sources.append((source_reference, source))

        payload = PerformanceResultPayload(
            **request.model_dump(),
            evidence_type=PERFORMANCE_EVIDENCE_TYPES[study_payload.study_type],
        )

        try:
            result, _ = self.repo.create_object(
                object_type="evidence",
                payload=payload.model_dump(),
                owner_user_id=request.owner_user_id,
                created_by=request.owner_user_id,
            )
            version = result.current_version
            self.repo.create_relation(
                source_uuid=result.object_uuid,
                source_version=version,
                target_uuid=study.object.object_uuid,
                target_version=request.study.object_version,
                relation_type="derived_from",
                created_by=request.owner_user_id,
                properties={"role": "performance_result_source"},
            )
            for source_reference, source in statistical_sources:
                self.repo.create_relation(
                    source_uuid=result.object_uuid,
                    source_version=version,
                    target_uuid=source.object.object_uuid,
                    target_version=source.version.version_no,
                    relation_type="derived_from",
                    created_by=request.owner_user_id,
                    properties={"role": _SOURCE_ROLE[source_reference.source_kind]},
                )
            for claim in claims:
                self.repo.create_relation(
                    source_uuid=result.object_uuid,
                    source_version=version,
                    target_uuid=claim.object.object_uuid,
                    target_version=claim.version.version_no,
                    relation_type="supported_by",
                    created_by=request.owner_user_id,
                )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return PerformanceResultResponse(
            object_uuid=result.uuid_hex,
            object_version=version,
            lifecycle_state=result.lifecycle_state,
            payload=payload,
        )

    def get_result(self, result_hex: str, version: int) -> PerformanceResultResponse:
        loaded = load_versioned_object(
            self.repo,
            result_hex,
            version,
            "evidence",
        )
        try:
            payload = PerformanceResultPayload(**loaded.payload)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Stored Performance Result payload is invalid"
            ) from exc

        return PerformanceResultResponse(
            object_uuid=loaded.object.uuid_hex,
            object_version=version,
            lifecycle_state=loaded.object.lifecycle_state,
            payload=payload,
        )

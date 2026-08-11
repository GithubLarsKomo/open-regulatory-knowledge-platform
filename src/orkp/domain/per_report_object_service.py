"""Persisted PER report aggregate and lifecycle service."""

import hashlib
from uuid import UUID

from pydantic import ValidationError

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    BaselineValidationError,
    InvalidLifecycleStateError,
    InvalidPersistedPayloadError,
    ObjectNotFoundError,
    ObjectTypeMismatchError,
    SelfApprovalNotAllowedError,
)
from orkp.domain.per_draft_service import PERDraftService
from orkp.domain.per_report_object_models import (
    PERReportCanonicalResponse,
    PERReportCreateRequest,
    PERReportObjectPayload,
    PERReportRegenerateRequest,
    PERReportResponse,
    canonicalize_per_draft,
)
from orkp.domain.risk_models import VersionedObjectReference


class PERReportObjectService:
    """Manage stable, versioned PER report RegulatoryObjects."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_report(self, request: PERReportCreateRequest) -> PERReportResponse:
        payload = self._build_payload(
            product_uuid=request.product_uuid,
            baseline_uuid=request.baseline_uuid,
            report_type=request.report_type,
        )
        try:
            report, version = self.repo.create_object(
                object_type="report",
                payload=payload.model_dump(mode="json"),
                owner_user_id=request.owner_user_id,
                created_by=request.owner_user_id,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise
        return self._response(report, version.version_no, payload)

    def get_report(self, report_hex: str) -> PERReportResponse:
        report, payload = self._load_current_report(report_hex)
        return self._response(report, report.current_version, payload)

    def get_canonical_json(self, report_hex: str) -> PERReportCanonicalResponse:
        report, payload = self._load_current_report(report_hex)
        canonical_json = canonicalize_per_draft(payload.draft)
        checksum = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        if checksum != payload.canonical_checksum_sha256:
            raise InvalidPersistedPayloadError(
                "Persisted PER report checksum does not match canonical draft"
            )
        return PERReportCanonicalResponse(
            report_uuid=report.uuid_hex,
            object_version=report.current_version,
            canonical_checksum_sha256=checksum,
            canonical_json=canonical_json,
        )

    def submit_for_review(
        self,
        report_hex: str,
        actor_user_id: str,
    ) -> PERReportResponse:
        report, _ = self._load_current_report(report_hex)
        self.repo.transition_state(report.object_uuid, "in_review", actor_user_id)
        self.repo.session.commit()
        return self.get_report(report_hex)

    def approve(
        self,
        report_hex: str,
        approver_user_id: str,
        comments: str | None = None,
    ) -> PERReportResponse:
        report, _ = self._load_current_report(report_hex)
        current_version = self.repo.get_version(
            report.object_uuid,
            report.current_version,
        )
        if report.owner_user_id == approver_user_id or (
            current_version is not None and current_version.created_by == approver_user_id
        ):
            raise SelfApprovalNotAllowedError(
                "PER report owner/current version author cannot approve the report"
            )
        self.repo.transition_state(
            report.object_uuid,
            "approved",
            approver_user_id,
            comments,
        )
        self.repo.session.commit()
        return self.get_report(report_hex)

    def regenerate_report(
        self,
        report_hex: str,
        request: PERReportRegenerateRequest,
    ) -> PERReportResponse:
        report, current_payload = self._load_current_report(report_hex)

        if report.lifecycle_state == "draft":
            payload = self._build_payload(
                product_uuid=current_payload.product.object_uuid,
                baseline_uuid=request.baseline_uuid,
                report_type=current_payload.report_type,
                predecessor_report=current_payload.predecessor_report,
            )
            try:
                version = self.repo.create_version(
                    report.object_uuid,
                    payload.model_dump(mode="json"),
                    request.actor_user_id,
                )
                self.repo.session.commit()
            except Exception:
                self.repo.session.rollback()
                raise
            return self._response(report, version.version_no, payload)

        if report.lifecycle_state in {"approved", "effective", "obsolete"}:
            predecessor = VersionedObjectReference(
                object_uuid=report.uuid_hex,
                object_version=report.current_version,
            )
            payload = self._build_payload(
                product_uuid=current_payload.product.object_uuid,
                baseline_uuid=request.baseline_uuid,
                report_type=current_payload.report_type,
                predecessor_report=predecessor,
            )
            try:
                successor, version = self.repo.create_object(
                    object_type="report",
                    payload=payload.model_dump(mode="json"),
                    owner_user_id=request.actor_user_id,
                    created_by=request.actor_user_id,
                )
                self.repo.session.commit()
            except Exception:
                self.repo.session.rollback()
                raise
            return self._response(successor, version.version_no, payload)

        raise InvalidLifecycleStateError(
            "PER report can be regenerated only while draft or after approval"
        )

    def _build_payload(
        self,
        product_uuid: str,
        baseline_uuid: str,
        report_type: str,
        predecessor_report: VersionedObjectReference | None = None,
    ) -> PERReportObjectPayload:
        draft = PERDraftService(self.repo).build_draft(baseline_uuid)
        if draft.schema_version != "per-draft-1.2" or draft.completeness_report is None:
            raise BaselineValidationError(
                "Persisted PER report requires a derived Report baseline with completeness"
            )
        try:
            normalized_product = UUID(product_uuid).hex
        except (ValueError, AttributeError, TypeError) as exc:
            raise BaselineValidationError("Invalid PER report Product UUID") from exc
        if draft.product.object_uuid != normalized_product:
            raise BaselineValidationError(
                "PER report Product does not match frozen Report baseline Product"
            )

        canonical_json = canonicalize_per_draft(draft)
        checksum = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        return PERReportObjectPayload(
            report_type=report_type,
            product={
                "object_uuid": draft.product.object_uuid,
                "object_version": draft.product.object_version,
            },
            baseline_uuid=draft.baseline_uuid,
            draft=draft,
            canonical_checksum_sha256=checksum,
            predecessor_report=predecessor_report,
        )

    def _load_current_report(self, report_hex: str):
        report = self.repo.get_by_uuid_hex(report_hex)
        if report is None:
            raise ObjectNotFoundError(f"PER report {report_hex} not found")
        if report.object_type != "report":
            raise ObjectTypeMismatchError(
                f"Expected report, got '{report.object_type}'"
            )
        version = self.repo.get_version(report.object_uuid, report.current_version)
        if version is None:
            raise ObjectNotFoundError(
                f"PER report {report.uuid_hex} version {report.current_version} not found"
            )
        try:
            payload = PERReportObjectPayload(**dict(version.payload_json or {}))
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                f"Persisted PER report {report.uuid_hex} payload is invalid"
            ) from exc
        return report, payload

    @staticmethod
    def _response(report, version_no: int, payload: PERReportObjectPayload):
        return PERReportResponse(
            report_uuid=report.uuid_hex,
            object_version=version_no,
            lifecycle_state=report.lifecycle_state,
            owner_user_id=report.owner_user_id,
            report_type=payload.report_type,
            product=payload.product,
            baseline_uuid=payload.baseline_uuid,
            canonical_checksum_sha256=payload.canonical_checksum_sha256,
            predecessor_report=payload.predecessor_report,
            draft=payload.draft,
        )

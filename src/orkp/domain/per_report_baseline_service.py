"""Derived PER Report baselines with frozen authoring and report context."""

from uuid import UUID

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    BaselineValidationError,
    InvalidObjectIdentifierError,
    ObjectNotFoundError,
)
from orkp.domain.per_completeness_models import PERCompletenessSnapshotPayload
from orkp.domain.per_content_models import (
    PERReportBaselineCreateRequest,
    PERReportBaselineResponse,
    PERReportContentPayload,
)
from orkp.domain.per_section_coverage_models import PERSectionCoverageSnapshotPayload
from orkp.domain.per_section_coverage_service import PERSectionCoverageService
from orkp.domain.per_section_coverage_traceability import (
    validate_cross_domain_section_traceability,
)
from orkp.domain.performance_gap_service import PerformanceClaimGapService
from orkp.domain.performance_report_service import PerformanceReportService
from orkp.domain.risk_models import VersionedObjectReference
from orkp.domain.versioned_loader import load_versioned_object


class PERReportBaselineService:
    """Freeze completeness, section coverage and optional AI text into a baseline."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_baseline(
        self,
        request: PERReportBaselineCreateRequest,
    ) -> PERReportBaselineResponse:
        source_baseline = self._load_baseline(request.performance_baseline_uuid)
        source_baseline_hex = UUID(bytes=source_baseline.baseline_uuid).hex

        performance_report = PerformanceReportService(self.repo).build_report(
            source_baseline_hex
        )
        source_items = self.repo.list_baseline_items(source_baseline.baseline_uuid)
        if any(
            item.object_type
            in {"report_content", "report_completeness", "report_section_coverage"}
            for item in source_items
        ):
            raise BaselineValidationError(
                "PER Report baseline source must be a Performance Evaluation baseline"
            )

        gap_report = PerformanceClaimGapService(self.repo).evaluate_product(
            performance_report.product.object_uuid
        )
        if (
            gap_report.product.object_uuid != performance_report.product.object_uuid
            or gap_report.product.object_version
            != performance_report.product.object_version
        ):
            raise BaselineValidationError(
                "Performance Evaluation baseline Product version is stale for completeness"
            )

        allowed_refs = {
            (UUID(bytes=item.object_uuid).hex, item.version_no) for item in source_items
        }
        for block in request.ai_draft_blocks:
            ref_keys = [
                (reference.object_uuid, reference.object_version)
                for reference in block.source_refs
            ]
            if len(ref_keys) != len(set(ref_keys)):
                raise BaselineValidationError(
                    f"AI draft block '{block.block_id}' contains duplicate source_refs"
                )
            missing = [key for key in ref_keys if key not in allowed_refs]
            if missing:
                raise BaselineValidationError(
                    f"AI draft block '{block.block_id}' references sources not frozen "
                    "in the Performance Evaluation baseline"
                )

        product_ref = VersionedObjectReference(
            object_uuid=performance_report.product.object_uuid,
            object_version=performance_report.product.object_version,
        )
        validate_cross_domain_section_traceability(self.repo, request)
        section_service = PERSectionCoverageService(self.repo)
        section_context = section_service.prepare_cross_domain_context(
            product_ref,
            request,
        )

        object_versions: dict[bytes, int] = {}
        for item in source_items:
            self._add_object_version(
                object_versions,
                item.object_uuid,
                item.version_no,
            )
        self._add_gap_context(object_versions, gap_report)
        for object_uuid, version in section_context.object_versions.items():
            self._add_object_version(object_versions, object_uuid, version)

        try:
            completeness_payload = PERCompletenessSnapshotPayload(
                source_performance_baseline_uuid=source_baseline_hex,
                gap_report=gap_report,
                owner_user_id=request.created_by_user_id,
            )
            completeness_object, completeness_version = self.repo.create_object(
                object_type="report_completeness",
                payload=completeness_payload.model_dump(mode="json"),
                owner_user_id=request.created_by_user_id,
                created_by=request.created_by_user_id,
            )
            self._add_object_version(
                object_versions,
                completeness_object.object_uuid,
                completeness_version.version_no,
            )
            completeness_ref = VersionedObjectReference(
                object_uuid=completeness_object.uuid_hex,
                object_version=completeness_version.version_no,
            )

            section_payload = PERSectionCoverageSnapshotPayload(
                source_performance_baseline_uuid=source_baseline_hex,
                sections=section_service.build_sections(
                    performance_report,
                    gap_report,
                    completeness_ref,
                    section_context,
                ),
                owner_user_id=request.created_by_user_id,
            )
            section_object, section_version = self.repo.create_object(
                object_type="report_section_coverage",
                payload=section_payload.model_dump(mode="json"),
                owner_user_id=request.created_by_user_id,
                created_by=request.created_by_user_id,
            )
            self._add_object_version(
                object_versions,
                section_object.object_uuid,
                section_version.version_no,
            )

            for block in request.ai_draft_blocks:
                payload = PERReportContentPayload(
                    block_id=block.block_id,
                    section_type=block.section_type,
                    text=block.text,
                    model_id=block.model_id,
                    source_performance_baseline_uuid=source_baseline_hex,
                    source_refs=block.source_refs,
                    owner_user_id=request.created_by_user_id,
                )
                content_object, content_version = self.repo.create_object(
                    object_type="report_content",
                    payload=payload.model_dump(mode="json"),
                    owner_user_id=request.created_by_user_id,
                    created_by=request.created_by_user_id,
                )
                self._add_object_version(
                    object_versions,
                    content_object.object_uuid,
                    content_version.version_no,
                )

            baseline = self.repo.create_baseline(
                name=request.name,
                description=request.description,
                object_versions=sorted(
                    object_versions.items(),
                    key=lambda item: (item[0].hex(), item[1]),
                ),
                created_by=request.created_by_user_id,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return PERReportBaselineResponse(
            baseline_uuid=UUID(bytes=baseline.baseline_uuid).hex,
            source_performance_baseline_uuid=source_baseline_hex,
            name=baseline.name,
            description=baseline.description,
            item_count=len(object_versions),
            ai_draft_block_count=len(request.ai_draft_blocks),
            completeness_snapshot_ref=completeness_ref,
            section_coverage_snapshot_ref={
                "object_uuid": section_object.uuid_hex,
                "object_version": section_version.version_no,
            },
            created_by_user_id=baseline.created_by,
        )

    def _add_gap_context(self, object_versions: dict[bytes, int], gap_report) -> None:
        for claim_item in gap_report.claims:
            claim = load_versioned_object(
                self.repo,
                claim_item.claim.object_uuid,
                claim_item.claim.object_version,
                "claim",
            )
            self._add_object_version(
                object_versions,
                claim.object.object_uuid,
                claim.version.version_no,
            )
            for finding in claim_item.findings:
                if finding.evidence is None:
                    continue
                evidence = load_versioned_object(
                    self.repo,
                    finding.evidence.object_uuid,
                    finding.evidence.object_version,
                    "evidence",
                )
                self._add_object_version(
                    object_versions,
                    evidence.object.object_uuid,
                    evidence.version.version_no,
                )

    @staticmethod
    def _add_object_version(
        object_versions: dict[bytes, int],
        object_uuid: bytes,
        version: int,
    ) -> None:
        existing = object_versions.get(object_uuid)
        if existing is not None and existing != version:
            raise BaselineValidationError(
                "PER Report baseline cannot contain conflicting versions of one object"
            )
        object_versions[object_uuid] = version

    def _load_baseline(self, baseline_hex: str):
        try:
            baseline_uuid = UUID(baseline_hex).bytes
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidObjectIdentifierError(
                f"Invalid baseline UUID format: {baseline_hex}"
            ) from exc
        baseline = self.repo.get_baseline(baseline_uuid)
        if baseline is None:
            raise ObjectNotFoundError(
                f"Baseline {UUID(bytes=baseline_uuid).hex} not found"
            )
        return baseline

"""Derived PER Report baselines with frozen AI draft content provenance."""

from uuid import UUID

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    BaselineValidationError,
    InvalidObjectIdentifierError,
    ObjectNotFoundError,
)
from orkp.domain.per_content_models import (
    PERReportBaselineCreateRequest,
    PERReportBaselineResponse,
    PERReportContentPayload,
)
from orkp.domain.performance_report_service import PerformanceReportService


class PERReportBaselineService:
    """Freeze external AI draft text together with an existing Performance baseline."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_baseline(
        self,
        request: PERReportBaselineCreateRequest,
    ) -> PERReportBaselineResponse:
        source_baseline = self._load_baseline(request.performance_baseline_uuid)
        source_baseline_hex = UUID(bytes=source_baseline.baseline_uuid).hex

        # Revalidate that the source is a usable Performance Evaluation baseline.
        PerformanceReportService(self.repo).build_report(source_baseline_hex)
        source_items = self.repo.list_baseline_items(source_baseline.baseline_uuid)
        if any(item.object_type == "report_content" for item in source_items):
            raise BaselineValidationError(
                "PER Report baseline source must be a Performance Evaluation baseline"
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

        object_versions = [(item.object_uuid, item.version_no) for item in source_items]
        try:
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
                object_versions.append(
                    (content_object.object_uuid, content_version.version_no)
                )

            baseline = self.repo.create_baseline(
                name=request.name,
                description=request.description,
                object_versions=sorted(
                    object_versions,
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
            created_by_user_id=baseline.created_by,
        )

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

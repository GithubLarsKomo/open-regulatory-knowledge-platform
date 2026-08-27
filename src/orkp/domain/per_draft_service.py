"""Baseline-only generation of deterministic PER draft manifests."""

import hashlib
import json
from uuid import UUID

from pydantic import ValidationError

from orkp.db.models import EventLog, GeneratedArtifact
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    BaselineValidationError,
    InvalidPersistedPayloadError,
)
from orkp.domain.per_completeness_models import (
    PERCompletenessReport,
    PERCompletenessSnapshotPayload,
)
from orkp.domain.per_content_models import (
    PERContentBlock,
    PERReportContentPayload,
)
from orkp.domain.per_draft_models import (
    PERDraftGenerationResponse,
    PERDraftPayload,
    PERTraceabilityEntry,
)
from orkp.domain.per_section_coverage_models import (
    PERSectionCoverageReport,
    PERSectionCoverageSnapshotPayload,
)
from orkp.domain.performance_report_models import PerformanceReportSnapshot
from orkp.domain.performance_report_service import PerformanceReportService
from orkp.domain.performance_result_models import PerformanceResultPayload
from orkp.domain.risk_models import VersionedObjectReference


_CONTENT_SECTION_ORDER = {
    "scientific_validity": 0,
    "analytical_performance": 1,
    "clinical_performance": 2,
}


class PERDraftService:
    """Compose a PER draft solely from a frozen report baseline."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def build_draft(self, baseline_hex: str) -> PERDraftPayload:
        """Build the canonical PER manifest without persisting an artifact."""
        performance_report = PerformanceReportService(self.repo).build_report(
            baseline_hex
        )
        baseline_uuid = UUID(performance_report.baseline_uuid).bytes
        items = self.repo.list_baseline_items(baseline_uuid)
        traceability = self._build_traceability(performance_report)
        content_blocks = self._build_content_blocks(performance_report, items)
        completeness_report = self._build_completeness_report(
            performance_report,
            items,
        )
        section_coverage = self._build_section_coverage(
            performance_report,
            items,
        )
        if (completeness_report is None) != (section_coverage is None):
            raise BaselineValidationError(
                "Derived PER Report baseline must freeze both completeness and section coverage"
            )
        return PERDraftPayload(
            schema_version=(
                "per-draft-1.3" if section_coverage is not None else "per-draft-1.1"
            ),
            baseline_uuid=performance_report.baseline_uuid,
            baseline_name=performance_report.baseline_name,
            baseline_description=performance_report.baseline_description,
            product=performance_report.product,
            performance_sections=performance_report,
            content_blocks=content_blocks,
            completeness_report=completeness_report,
            section_coverage=section_coverage,
            traceability_appendix=traceability,
        )

    def generate_draft(
        self,
        baseline_hex: str,
        generated_by_user_id: str,
    ) -> PERDraftGenerationResponse:
        draft = self.build_draft(baseline_hex)
        baseline_uuid = UUID(draft.baseline_uuid).bytes
        canonical_json = json.dumps(
            draft.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        checksum = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

        try:
            artifact = GeneratedArtifact(
                baseline_uuid=baseline_uuid,
                artifact_type="per_draft",
                format="json",
                file_path=None,
                checksum=checksum,
                generated_by=generated_by_user_id,
            )
            self.repo.session.add(artifact)
            self.repo.session.flush()
            artifact_uuid = UUID(bytes=artifact.artifact_uuid).hex
            self.repo.session.add(
                EventLog(
                    aggregate_type="baseline",
                    aggregate_uuid=baseline_uuid,
                    event_type="artifact_generated",
                    event_data={
                        "artifact_uuid": artifact_uuid,
                        "artifact_type": artifact.artifact_type,
                        "format": artifact.format,
                        "checksum": checksum,
                    },
                    actor_user_id=generated_by_user_id,
                )
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return PERDraftGenerationResponse(
            artifact_uuid=artifact_uuid,
            baseline_uuid=draft.baseline_uuid,
            checksum_sha256=checksum,
            canonical_json=canonical_json,
            draft=draft,
        )

    def _build_completeness_report(
        self,
        report,
        items,
    ) -> PERCompletenessReport | None:
        completeness_items = [
            item for item in items if item.object_type == "report_completeness"
        ]
        if not completeness_items:
            return None
        if len(completeness_items) != 1:
            raise BaselineValidationError(
                "PER Report baseline must contain exactly one completeness snapshot"
            )

        item = completeness_items[0]
        try:
            payload = PERCompletenessSnapshotPayload(**dict(item.snapshot_json or {}))
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Frozen report_completeness payload is invalid"
            ) from exc

        if (
            payload.gap_report.product.object_uuid != report.product.object_uuid
            or payload.gap_report.product.object_version
            != report.product.object_version
        ):
            raise BaselineValidationError(
                "Frozen completeness Product does not match PER Product"
            )

        frozen_refs = {
            (UUID(bytes=frozen.object_uuid).hex, frozen.version_no) for frozen in items
        }
        for claim_item in payload.gap_report.claims:
            claim_key = (
                claim_item.claim.object_uuid,
                claim_item.claim.object_version,
            )
            if claim_key not in frozen_refs:
                raise BaselineValidationError(
                    "Frozen completeness report references a Claim outside the baseline"
                )
            for finding in claim_item.findings:
                if finding.evidence is None:
                    continue
                evidence_key = (
                    finding.evidence.object_uuid,
                    finding.evidence.object_version,
                )
                if evidence_key not in frozen_refs:
                    raise BaselineValidationError(
                        "Frozen completeness report references Evidence outside the baseline"
                    )

        return PERCompletenessReport(
            snapshot_ref={
                "object_uuid": UUID(bytes=item.object_uuid).hex,
                "object_version": item.version_no,
            },
            gap_report=payload.gap_report,
        )

    def _build_section_coverage(
        self,
        report,
        items,
    ) -> PERSectionCoverageReport | None:
        coverage_items = [
            item for item in items if item.object_type == "report_section_coverage"
        ]
        if not coverage_items:
            return None
        if len(coverage_items) != 1:
            raise BaselineValidationError(
                "PER Report baseline must contain exactly one section coverage snapshot"
            )
        item = coverage_items[0]
        try:
            payload = PERSectionCoverageSnapshotPayload(
                **dict(item.snapshot_json or {})
            )
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Frozen report_section_coverage payload is invalid"
            ) from exc

        frozen_refs = {
            (UUID(bytes=frozen.object_uuid).hex, frozen.version_no) for frozen in items
        }
        product_key = (report.product.object_uuid, report.product.object_version)
        cover = payload.sections[0]
        if product_key not in {
            (reference.object_uuid, reference.object_version)
            for reference in cover.source_refs
        }:
            raise BaselineValidationError(
                "Frozen Cover Page section does not reference the PER Product"
            )
        for section in payload.sections:
            for reference in section.source_refs:
                key = (reference.object_uuid, reference.object_version)
                if key not in frozen_refs:
                    raise BaselineValidationError(
                        f"Frozen canonical section '{section.section_id}' references "
                        "an object outside the baseline"
                    )
        return PERSectionCoverageReport(
            snapshot_ref={
                "object_uuid": UUID(bytes=item.object_uuid).hex,
                "object_version": item.version_no,
            },
            sections=payload.sections,
        )

    def _build_content_blocks(
        self,
        report,
        items,
    ) -> list[PERContentBlock]:
        allowed_refs = self._report_reference_keys(report)
        blocks: list[PERContentBlock] = []

        for section in report.sections:
            for item in section.items:
                try:
                    result = PerformanceResultPayload(
                        **item.performance_result.snapshot
                    )
                except ValidationError as exc:
                    raise InvalidPersistedPayloadError(
                        "Frozen Performance Result payload is invalid"
                    ) from exc
                if result.interpretation:
                    blocks.append(
                        PERContentBlock(
                            block_id=(
                                f"approved:{item.performance_result.object_uuid}:"
                                f"v{item.performance_result.object_version}"
                            ),
                            section_type=section.section_type,
                            text=result.interpretation,
                            origin="approved_source",
                            review_status="source_approved",
                            source_refs=[self._reference(item.performance_result)],
                        )
                    )

        for item in items:
            if item.object_type != "report_content":
                continue
            try:
                payload = PERReportContentPayload(**dict(item.snapshot_json or {}))
            except ValidationError as exc:
                raise InvalidPersistedPayloadError(
                    "Frozen report_content payload is invalid"
                ) from exc
            if payload.block_id.startswith("approved:"):
                raise BaselineValidationError(
                    "AI report_content block_id uses reserved 'approved:' prefix"
                )
            missing = [
                reference
                for reference in payload.source_refs
                if (reference.object_uuid, reference.object_version) not in allowed_refs
            ]
            if missing:
                raise BaselineValidationError(
                    f"AI report_content '{payload.block_id}' references sources outside "
                    "the frozen Performance context"
                )
            blocks.append(
                PERContentBlock(
                    block_id=payload.block_id,
                    section_type=payload.section_type,
                    text=payload.text,
                    origin=payload.origin,
                    review_status=payload.review_status,
                    source_refs=payload.source_refs,
                    content_ref=VersionedObjectReference(
                        object_uuid=UUID(bytes=item.object_uuid).hex,
                        object_version=item.version_no,
                    ),
                    model_id=payload.model_id,
                )
            )

        block_ids = [block.block_id for block in blocks]
        if len(block_ids) != len(set(block_ids)):
            raise BaselineValidationError(
                "PER draft baseline contains duplicate content block IDs"
            )
        return sorted(
            blocks,
            key=lambda block: (
                _CONTENT_SECTION_ORDER[block.section_type],
                0 if block.origin == "approved_source" else 1,
                block.block_id,
            ),
        )

    @classmethod
    def _report_reference_keys(cls, report) -> set[tuple[str, int]]:
        refs = {
            (report.product.object_uuid, report.product.object_version),
        }
        for section in report.sections:
            for item in section.items:
                snapshots = [
                    item.performance_result,
                    item.study,
                    *item.claims,
                    *item.statistical_sources,
                ]
                refs.update(
                    (snapshot.object_uuid, snapshot.object_version)
                    for snapshot in snapshots
                )
        return refs

    @classmethod
    def _build_traceability(cls, report) -> list[PERTraceabilityEntry]:
        entries: list[PERTraceabilityEntry] = []
        for section in report.sections:
            for item in section.items:
                entries.append(
                    PERTraceabilityEntry(
                        section_type=section.section_type,
                        performance_result=cls._reference(item.performance_result),
                        study=cls._reference(item.study),
                        claims=[cls._reference(snapshot) for snapshot in item.claims],
                        statistical_sources=[
                            cls._reference(snapshot)
                            for snapshot in item.statistical_sources
                        ],
                    )
                )
        return entries

    @staticmethod
    def _reference(snapshot: PerformanceReportSnapshot) -> VersionedObjectReference:
        return VersionedObjectReference(
            object_uuid=snapshot.object_uuid,
            object_version=snapshot.object_version,
        )

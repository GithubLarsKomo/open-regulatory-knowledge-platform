"""Frozen-baseline generation of reproducible Performance Evaluation sections."""

import hashlib
import json
from uuid import UUID

from pydantic import ValidationError

from orkp.db.models import EventLog, GeneratedArtifact
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    BaselineValidationError,
    InvalidObjectIdentifierError,
    InvalidPersistedPayloadError,
    ObjectNotFoundError,
)
from orkp.domain.performance_models import PerformanceStudyPayload
from orkp.domain.performance_report_models import (
    PerformanceReportBaselineCreateRequest,
    PerformanceReportBaselineResponse,
    PerformanceReportGenerationResponse,
    PerformanceReportPayload,
    PerformanceReportSection,
    PerformanceReportSectionItem,
    PerformanceReportSnapshot,
)
from orkp.domain.performance_report_traceability import (
    validate_performance_result_traceability,
)
from orkp.domain.performance_result_models import PerformanceResultPayload
from orkp.domain.versioned_loader import load_versioned_object


_SECTION_BY_EVIDENCE_TYPE = {
    "scientific_validity": "scientific_validity",
    "analytical_study": "analytical_performance",
    "clinical_study": "clinical_performance",
}
_SECTION_ORDER = {
    "scientific_validity": 0,
    "analytical_performance": 1,
    "clinical_performance": 2,
}


class PerformanceReportService:
    """Freeze approved Performance context and render deterministic PER sections."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_baseline(
        self,
        request: PerformanceReportBaselineCreateRequest,
    ) -> PerformanceReportBaselineResponse:
        object_versions = self._validate_baseline_context(request)
        try:
            baseline = self.repo.create_baseline(
                name=request.name,
                description=request.description,
                object_versions=object_versions,
                created_by=request.created_by_user_id,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return PerformanceReportBaselineResponse(
            baseline_uuid=UUID(bytes=baseline.baseline_uuid).hex,
            name=baseline.name,
            description=baseline.description,
            product=request.product,
            evidence_count=len(request.evidence),
            item_count=len(object_versions),
            created_by_user_id=baseline.created_by,
        )

    def get_baseline(self, baseline_hex: str) -> PerformanceReportBaselineResponse:
        baseline = self._load_baseline(baseline_hex)
        items = self.repo.list_baseline_items(baseline.baseline_uuid)
        product_items = [item for item in items if item.object_type == "product"]
        result_items = [
            item
            for item in items
            if item.object_type == "evidence"
            and self._is_performance_result(item.snapshot_json)
        ]
        if len(product_items) != 1 or not result_items:
            raise BaselineValidationError(
                "Baseline is not a valid Performance Evaluation baseline"
            )
        product = product_items[0]
        return PerformanceReportBaselineResponse(
            baseline_uuid=UUID(bytes=baseline.baseline_uuid).hex,
            name=baseline.name,
            description=baseline.description,
            product={
                "object_uuid": UUID(bytes=product.object_uuid).hex,
                "object_version": product.version_no,
            },
            evidence_count=len(result_items),
            item_count=len(items),
            created_by_user_id=baseline.created_by,
        )

    def build_report(self, baseline_hex: str) -> PerformanceReportPayload:
        """Build deterministic Performance sections from frozen snapshots only."""
        baseline = self._load_baseline(baseline_hex)
        items = self.repo.list_baseline_items(baseline.baseline_uuid)
        snapshots = {
            (UUID(bytes=item.object_uuid).hex, item.version_no): self._snapshot(item)
            for item in items
        }
        product_snapshots = [
            snapshot
            for snapshot in snapshots.values()
            if snapshot.object_type == "product"
        ]
        if len(product_snapshots) != 1:
            raise BaselineValidationError(
                "Performance Evaluation baseline must contain exactly one Product"
            )

        grouped: dict[str, list[PerformanceReportSectionItem]] = {}
        for snapshot in snapshots.values():
            if snapshot.object_type != "evidence":
                continue
            try:
                result = PerformanceResultPayload(**snapshot.snapshot)
            except ValidationError:
                continue

            section_type = _SECTION_BY_EVIDENCE_TYPE[result.evidence_type]
            study = self._require_snapshot(snapshots, result.study)
            claims = [self._require_snapshot(snapshots, ref) for ref in result.claims]
            statistical_sources = [
                self._require_snapshot(snapshots, source.evidence)
                for source in result.statistical_sources
            ]
            grouped.setdefault(section_type, []).append(
                PerformanceReportSectionItem(
                    performance_result=snapshot,
                    study=study,
                    claims=sorted(
                        claims,
                        key=lambda item: (item.object_uuid, item.object_version),
                    ),
                    statistical_sources=sorted(
                        statistical_sources,
                        key=lambda item: (item.object_uuid, item.object_version),
                    ),
                )
            )

        if not grouped:
            raise BaselineValidationError(
                "Performance Evaluation baseline contains no Performance Results"
            )

        sections = [
            PerformanceReportSection(
                section_type=section_type,
                items=sorted(
                    section_items,
                    key=lambda item: (
                        item.performance_result.snapshot.get("result_id", ""),
                        item.performance_result.object_uuid,
                        item.performance_result.object_version,
                    ),
                ),
            )
            for section_type, section_items in sorted(
                grouped.items(), key=lambda item: _SECTION_ORDER[item[0]]
            )
        ]
        return PerformanceReportPayload(
            baseline_uuid=UUID(bytes=baseline.baseline_uuid).hex,
            baseline_name=baseline.name,
            baseline_description=baseline.description,
            product=product_snapshots[0],
            sections=sections,
        )

    def generate_sections(
        self,
        baseline_hex: str,
        generated_by_user_id: str,
    ) -> PerformanceReportGenerationResponse:
        """Generate canonical PER sections exclusively from frozen snapshots."""
        report = self.build_report(baseline_hex)
        baseline = self._load_baseline(baseline_hex)
        canonical_json = json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        checksum = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

        try:
            artifact = GeneratedArtifact(
                baseline_uuid=baseline.baseline_uuid,
                artifact_type="performance_evaluation_sections",
                format="json",
                file_path=None,
                checksum=checksum,
                generated_by=generated_by_user_id,
            )
            self.repo.session.add(artifact)
            self.repo.session.flush()
            self.repo.session.add(
                EventLog(
                    aggregate_type="baseline",
                    aggregate_uuid=baseline.baseline_uuid,
                    event_type="artifact_generated",
                    event_data={
                        "artifact_uuid": UUID(bytes=artifact.artifact_uuid).hex,
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

        return PerformanceReportGenerationResponse(
            artifact_uuid=UUID(bytes=artifact.artifact_uuid).hex,
            baseline_uuid=UUID(bytes=baseline.baseline_uuid).hex,
            checksum_sha256=checksum,
            canonical_json=canonical_json,
            report=report,
        )

    def _validate_baseline_context(
        self,
        request: PerformanceReportBaselineCreateRequest,
    ) -> list[tuple[bytes, int]]:
        object_versions: dict[bytes, int] = {}

        product = load_versioned_object(
            self.repo,
            request.product.object_uuid,
            request.product.object_version,
            "product",
            allowed_lifecycle_states=["approved", "effective"],
        )
        if product.object.current_version != request.product.object_version:
            raise BaselineValidationError(
                "PER baseline must reference the current Product version"
            )
        if product.version.status != "approved":
            raise BaselineValidationError(
                "PER baseline Product version is not approved"
            )
        self._add_object_version(
            object_versions,
            product.object.object_uuid,
            product.version.version_no,
        )

        for reference in request.evidence:
            result = load_versioned_object(
                self.repo,
                reference.object_uuid,
                reference.object_version,
                "evidence",
                allowed_lifecycle_states=["approved", "effective"],
            )
            if result.object.current_version != reference.object_version:
                raise BaselineValidationError(
                    "PER baseline must use current Performance Result Evidence versions"
                )
            if result.version.status != "approved":
                raise BaselineValidationError(
                    "PER baseline Performance Result Evidence version is not approved"
                )
            try:
                payload = PerformanceResultPayload(**result.payload)
            except ValidationError as exc:
                raise InvalidPersistedPayloadError(
                    "Selected Evidence is not a valid Performance Result"
                ) from exc

            validate_performance_result_traceability(
                self.repo,
                result.object.object_uuid,
                result.version.version_no,
                payload,
            )
            self._add_object_version(
                object_versions,
                result.object.object_uuid,
                result.version.version_no,
            )
            self._add_study_context(object_versions, payload)
            self._add_claim_context(object_versions, payload)
            self._add_statistical_source_context(object_versions, payload)

        return sorted(
            object_versions.items(), key=lambda item: (item[0].hex(), item[1])
        )

    def _add_study_context(
        self,
        object_versions: dict[bytes, int],
        payload: PerformanceResultPayload,
    ) -> None:
        study = load_versioned_object(
            self.repo,
            payload.study.object_uuid,
            payload.study.object_version,
            "study",
        )
        try:
            PerformanceStudyPayload(**study.payload)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Performance Result references an invalid Performance Study"
            ) from exc
        self._add_object_version(
            object_versions,
            study.object.object_uuid,
            study.version.version_no,
        )

    def _add_claim_context(
        self,
        object_versions: dict[bytes, int],
        payload: PerformanceResultPayload,
    ) -> None:
        for reference in payload.claims:
            claim = load_versioned_object(
                self.repo,
                reference.object_uuid,
                reference.object_version,
                "claim",
                allowed_lifecycle_states=["approved", "effective"],
            )
            if claim.object.current_version != reference.object_version:
                raise BaselineValidationError(
                    "PER baseline Performance Results must reference current Claim versions"
                )
            if claim.version.status != "approved":
                raise BaselineValidationError(
                    "PER baseline referenced Claim version is not approved"
                )
            self._add_object_version(
                object_versions,
                claim.object.object_uuid,
                claim.version.version_no,
            )

    def _add_statistical_source_context(
        self,
        object_versions: dict[bytes, int],
        payload: PerformanceResultPayload,
    ) -> None:
        for source_reference in payload.statistical_sources:
            source = load_versioned_object(
                self.repo,
                source_reference.evidence.object_uuid,
                source_reference.evidence.object_version,
                "evidence",
            )
            self._add_object_version(
                object_versions,
                source.object.object_uuid,
                source.version.version_no,
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
                "PER baseline cannot contain conflicting versions of the same object"
            )
        object_versions[object_uuid] = version

    @staticmethod
    def _snapshot(item) -> PerformanceReportSnapshot:
        return PerformanceReportSnapshot(
            object_uuid=UUID(bytes=item.object_uuid).hex,
            object_type=item.object_type,
            object_version=item.version_no,
            snapshot=dict(item.snapshot_json or {}),
        )

    @staticmethod
    def _is_performance_result(snapshot: dict | None) -> bool:
        try:
            PerformanceResultPayload(**dict(snapshot or {}))
        except ValidationError:
            return False
        return True

    @staticmethod
    def _require_snapshot(snapshots, reference) -> PerformanceReportSnapshot:
        snapshot = snapshots.get((reference.object_uuid, reference.object_version))
        if snapshot is None:
            raise BaselineValidationError(
                "PER baseline is missing referenced frozen provenance context"
            )
        return snapshot

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

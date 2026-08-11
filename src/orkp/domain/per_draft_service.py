"""Baseline-only generation of deterministic PER draft manifests."""

import hashlib
import json
from uuid import UUID

from orkp.db.models import EventLog, GeneratedArtifact
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import InvalidObjectIdentifierError, ObjectNotFoundError
from orkp.domain.per_draft_models import (
    PERDraftGenerationResponse,
    PERDraftPayload,
    PERTraceabilityEntry,
)
from orkp.domain.performance_report_models import PerformanceReportSnapshot
from orkp.domain.performance_report_service import PerformanceReportService
from orkp.domain.risk_models import VersionedObjectReference


class PERDraftService:
    """Compose a PER draft solely from a frozen Performance Evaluation baseline."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def generate_draft(
        self,
        baseline_hex: str,
        generated_by_user_id: str,
    ) -> PERDraftGenerationResponse:
        performance_report = PerformanceReportService(self.repo).build_report(baseline_hex)
        baseline = self._load_baseline(baseline_hex)
        traceability = self._build_traceability(performance_report)
        draft = PERDraftPayload(
            baseline_uuid=performance_report.baseline_uuid,
            baseline_name=performance_report.baseline_name,
            baseline_description=performance_report.baseline_description,
            product=performance_report.product,
            performance_sections=performance_report,
            traceability_appendix=traceability,
        )
        canonical_json = json.dumps(
            draft.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        checksum = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

        try:
            artifact = GeneratedArtifact(
                baseline_uuid=baseline.baseline_uuid,
                artifact_type="per_draft",
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

        return PERDraftGenerationResponse(
            artifact_uuid=UUID(bytes=artifact.artifact_uuid).hex,
            baseline_uuid=UUID(bytes=baseline.baseline_uuid).hex,
            checksum_sha256=checksum,
            canonical_json=canonical_json,
            draft=draft,
        )

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

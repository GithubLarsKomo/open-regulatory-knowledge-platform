"""Risk-specific frozen-baseline and reproducible report generation service."""

import hashlib
import json
from uuid import UUID

from orkp.db.models import EventLog, GeneratedArtifact
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    BaselineValidationError,
    InvalidObjectIdentifierError,
    ObjectNotFoundError,
)
from orkp.domain.risk_report_models import (
    RiskReportBaselineCreateRequest,
    RiskReportBaselineResponse,
    RiskReportGenerationResponse,
    RiskReportItemSnapshot,
    RiskReportPayload,
)


class RiskReportService:
    """Freeze Risk report inputs and render deterministic baseline-only output."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_baseline(
        self,
        request: RiskReportBaselineCreateRequest,
    ) -> RiskReportBaselineResponse:
        object_versions = self._validate_baseline_objects(request)
        try:
            baseline = self.repo.create_baseline(
                name=request.name,
                description=request.description,
                object_versions=object_versions,
                created_by=request.created_by_user_id,
            )
            response = RiskReportBaselineResponse(
                baseline_uuid=UUID(bytes=baseline.baseline_uuid).hex,
                name=baseline.name,
                description=baseline.description,
                item_count=len(object_versions),
                created_by_user_id=baseline.created_by,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return response

    def get_baseline(self, baseline_hex: str) -> RiskReportBaselineResponse:
        baseline = self._load_baseline(baseline_hex)
        items = self.repo.list_baseline_items(baseline.baseline_uuid)
        return RiskReportBaselineResponse(
            baseline_uuid=UUID(bytes=baseline.baseline_uuid).hex,
            name=baseline.name,
            description=baseline.description,
            item_count=len(items),
            created_by_user_id=baseline.created_by,
        )

    def generate_report(
        self,
        baseline_hex: str,
        generated_by_user_id: str,
    ) -> RiskReportGenerationResponse:
        """Generate canonical report bytes exclusively from frozen baseline snapshots."""
        baseline = self._load_baseline(baseline_hex)
        items = self.repo.list_baseline_items(baseline.baseline_uuid)
        report_items = sorted(
            (
                RiskReportItemSnapshot(
                    object_uuid=UUID(bytes=item.object_uuid).hex,
                    object_type=item.object_type,
                    object_version=item.version_no,
                    snapshot=dict(item.snapshot_json or {}),
                )
                for item in items
            ),
            key=lambda item: (
                item.object_type,
                item.object_uuid,
                item.object_version,
            ),
        )
        report = RiskReportPayload(
            baseline_uuid=UUID(bytes=baseline.baseline_uuid).hex,
            baseline_name=baseline.name,
            baseline_description=baseline.description,
            items=report_items,
        )
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
                artifact_type="risk_management_report",
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

        return RiskReportGenerationResponse(
            artifact_uuid=UUID(bytes=artifact.artifact_uuid).hex,
            baseline_uuid=UUID(bytes=baseline.baseline_uuid).hex,
            checksum_sha256=checksum,
            canonical_json=canonical_json,
            report=report,
        )

    def _validate_baseline_objects(
        self,
        request: RiskReportBaselineCreateRequest,
    ) -> list[tuple[bytes, int]]:
        seen: set[tuple[bytes, int]] = set()
        seen_objects: set[bytes] = set()
        object_versions: list[tuple[bytes, int]] = []
        approved_risk_roots = 0

        for reference in request.objects:
            try:
                normalized = UUID(reference.object_uuid).hex
                object_uuid = UUID(normalized).bytes
            except (ValueError, AttributeError, TypeError) as exc:
                raise InvalidObjectIdentifierError(
                    f"Invalid UUID format: {reference.object_uuid}"
                ) from exc

            key = (object_uuid, reference.object_version)
            if key in seen:
                raise BaselineValidationError(
                    "Risk Report Baseline contains a duplicate object/version reference"
                )
            if object_uuid in seen_objects:
                raise BaselineValidationError(
                    "Risk Report Baseline must contain exactly one version per object"
                )
            seen.add(key)
            seen_objects.add(object_uuid)

            obj = self.repo.get_by_uuid_hex(normalized)
            if obj is None:
                raise ObjectNotFoundError(f"Object {normalized} not found")
            version = self.repo.get_version(object_uuid, reference.object_version)
            if version is None:
                raise BaselineValidationError(
                    f"Version {reference.object_version} of object {normalized} does not exist"
                )

            if obj.object_type == "risk_analysis":
                if obj.current_version != reference.object_version:
                    raise BaselineValidationError(
                        "Risk Report Baseline must use the current Risk Analysis version"
                    )
                if obj.lifecycle_state not in {"approved", "effective"}:
                    raise BaselineValidationError(
                        "Risk Report Baseline requires approved/effective Risk Analysis roots"
                    )
                if version.status != "approved":
                    raise BaselineValidationError(
                        "Risk Report Baseline Risk Analysis version is not approved"
                    )
                approved_risk_roots += 1

            object_versions.append(key)

        if approved_risk_roots == 0:
            raise BaselineValidationError(
                "Risk Report Baseline requires at least one approved/effective Risk Analysis"
            )

        return sorted(object_versions, key=lambda item: (item[0].hex(), item[1]))

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

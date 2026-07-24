"""Service for baseline-pinned deterministic PER report generation."""

import json
import uuid
from typing import Any

from pydantic import ValidationError

from orkp.db.models import _bin_to_str
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    BaselineValidationError,
    InvalidObjectIdentifierError,
    InvalidPersistedPayloadError,
    ObjectNotFoundError,
    ObjectTypeMismatchError,
)
from orkp.domain.per_report_models import (
    PERCompletenessGap,
    PERContentBlock,
    PERReportPayload,
    PERReportResponse,
    PERSection,
    PERTraceabilityEntry,
)


_SECTION_TITLES = {
    "cover_page": "Cover Page",
    "intended_purpose": "Intended Purpose",
    "scientific_validity": "Scientific Validity",
    "analytical_performance": "Analytical Performance",
    "clinical_performance": "Clinical Performance",
    "claims_and_evidence": "Claims and Evidence",
    "risk_benefit_analysis": "Risk-Benefit Analysis",
    "pmpf_summary": "PMPF Summary",
    "traceability_appendix": "Traceability Appendix",
    "completeness_report": "Completeness Report",
}

_REQUIRED_SOURCE_TYPES = {
    "scientific_validity": {"evidence"},
    "analytical_performance": {"performance_study", "evidence"},
    "clinical_performance": {"performance_study", "evidence"},
    "claims_and_evidence": {"claim", "evidence"},
    "risk_benefit_analysis": {"risk_analysis", "residual_risk_evaluation"},
}


class PERReportService:
    """Generate and retrieve persisted PER report regulatory objects."""

    object_type = "per_report"

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    @staticmethod
    def _uuid_bytes(value: str, label: str) -> bytes:
        try:
            return uuid.UUID(value).bytes
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidObjectIdentifierError(f"Invalid {label}: {value}") from exc

    def generate(
        self,
        product_uuid: str,
        baseline_uuid: str,
        report_type: str,
        generated_by: str,
    ) -> PERReportResponse:
        product = self.repo.get_by_uuid_hex(product_uuid)
        if product is None:
            raise ObjectNotFoundError(f"Product {product_uuid} not found")
        if product.object_type != "product":
            raise ObjectTypeMismatchError(
                f"Object {product_uuid} is '{product.object_type}', expected 'product'"
            )

        baseline_raw = self._uuid_bytes(baseline_uuid, "baseline_uuid")
        baseline = self.repo.get_baseline(baseline_raw)
        if baseline is None:
            raise ObjectNotFoundError(f"Baseline {baseline_uuid} not found")

        items = self.repo.list_baseline_items(baseline_raw)
        product_item = next(
            (item for item in items if item.object_uuid == product.object_uuid), None
        )
        if product_item is None:
            raise BaselineValidationError(
                f"Baseline {baseline_uuid} does not contain product {product_uuid}"
            )

        product_version = self.repo.get_version(
            product_item.object_uuid, product_item.version_no
        )
        if product_version is None or product_version.status != "approved":
            raise BaselineValidationError(
                "PER generation requires an approved product version in the baseline"
            )

        approved_items = []
        for item in items:
            version = self.repo.get_version(item.object_uuid, item.version_no)
            if version is not None and version.status == "approved":
                approved_items.append((item, version))

        payload = self._build_payload(
            report_type=report_type,
            product_uuid=_bin_to_str(product.object_uuid),
            product_item=product_item,
            baseline_uuid=_bin_to_str(baseline_raw),
            approved_items=approved_items,
        )

        try:
            report_obj, _ = self.repo.create_object(
                object_type=self.object_type,
                payload=payload.model_dump(mode="json"),
                owner_user_id=generated_by,
                created_by=generated_by,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return PERReportResponse(
            report_uuid=report_obj.uuid_hex,
            report_version=report_obj.current_version,
            lifecycle_state=report_obj.lifecycle_state,
            payload=payload,
        )

    def get(self, report_uuid: str) -> PERReportResponse:
        obj = self.repo.get_by_uuid_hex(report_uuid)
        if obj is None:
            raise ObjectNotFoundError(f"PER report {report_uuid} not found")
        if obj.object_type != self.object_type:
            raise ObjectTypeMismatchError(
                f"Object {report_uuid} is '{obj.object_type}', expected '{self.object_type}'"
            )
        version = self.repo.get_version(obj.object_uuid, obj.current_version)
        if version is None:
            raise ObjectNotFoundError(
                f"Version {obj.current_version} of PER report {report_uuid} not found"
            )
        try:
            payload = PERReportPayload(**version.payload_json)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                f"Stored PER report {report_uuid} payload is invalid"
            ) from exc
        return PERReportResponse(
            report_uuid=obj.uuid_hex,
            report_version=obj.current_version,
            lifecycle_state=obj.lifecycle_state,
            payload=payload,
        )

    def canonical_json(self, report_uuid: str) -> str:
        """Return deterministic JSON without non-canonical object metadata."""
        payload = self.get(report_uuid).payload.model_dump(mode="json")
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _build_payload(
        self,
        report_type: str,
        product_uuid: str,
        product_item: Any,
        baseline_uuid: str,
        approved_items: list[tuple[Any, Any]],
    ) -> PERReportPayload:
        by_type: dict[str, list[tuple[Any, Any]]] = {}
        traceability: list[PERTraceabilityEntry] = []
        for item, version in approved_items:
            by_type.setdefault(item.object_type, []).append((item, version))
            traceability.append(
                PERTraceabilityEntry(
                    object_uuid=_bin_to_str(item.object_uuid),
                    object_type=item.object_type,
                    version=item.version_no,
                    version_status=version.status,
                )
            )
        traceability.sort(key=lambda entry: (entry.object_type, entry.object_uuid, entry.version))

        product_payload = product_item.snapshot_json or {}
        sections = [
            PERSection(
                section_key="cover_page",
                title=_SECTION_TITLES["cover_page"],
                blocks=[
                    PERContentBlock(
                        block_key="product_metadata",
                        content={
                            "product_id": product_payload.get("product_id"),
                            "name": product_payload.get("name"),
                            "legal_manufacturer": product_payload.get("legal_manufacturer"),
                        },
                        provenance="approved",
                        source_object_uuid=product_uuid,
                        source_version=product_item.version_no,
                    )
                ],
            ),
            PERSection(
                section_key="intended_purpose",
                title=_SECTION_TITLES["intended_purpose"],
                blocks=[
                    PERContentBlock(
                        block_key="intended_purpose",
                        content=product_payload.get("intended_purpose", ""),
                        provenance="approved",
                        source_object_uuid=product_uuid,
                        source_version=product_item.version_no,
                    )
                ],
            ),
        ]

        section_sources = {
            "scientific_validity": by_type.get("evidence", []),
            "analytical_performance": by_type.get("performance_study", []),
            "clinical_performance": by_type.get("performance_study", []),
            "claims_and_evidence": by_type.get("claim", []) + by_type.get("evidence", []),
            "risk_benefit_analysis": by_type.get("risk_analysis", [])
            + by_type.get("residual_risk_evaluation", []),
            "pmpf_summary": by_type.get("pmpf", []) + by_type.get("pms", []),
        }
        for section_key, source_items in section_sources.items():
            blocks = [
                PERContentBlock(
                    block_key=f"{item.object_type}:{_bin_to_str(item.object_uuid)}:{item.version_no}",
                    content=item.snapshot_json,
                    provenance="approved",
                    source_object_uuid=_bin_to_str(item.object_uuid),
                    source_version=item.version_no,
                )
                for item, _version in sorted(
                    source_items,
                    key=lambda pair: (
                        pair[0].object_type,
                        _bin_to_str(pair[0].object_uuid),
                        pair[0].version_no,
                    ),
                )
            ]
            sections.append(
                PERSection(
                    section_key=section_key,
                    title=_SECTION_TITLES[section_key],
                    blocks=blocks,
                )
            )

        gaps: list[PERCompletenessGap] = []
        for section_key, required_types in _REQUIRED_SOURCE_TYPES.items():
            available_types = {
                item.object_type for item, _version in section_sources[section_key]
            }
            if not available_types.intersection(required_types):
                gaps.append(
                    PERCompletenessGap(
                        code=f"PER-MISSING-{section_key.upper().replace('_', '-')}",
                        section_key=section_key,
                        message=(
                            f"No approved baseline source found for {section_key}; "
                            f"expected one of {sorted(required_types)}"
                        ),
                    )
                )

        sections.extend(
            [
                PERSection(
                    section_key="traceability_appendix",
                    title=_SECTION_TITLES["traceability_appendix"],
                    blocks=[
                        PERContentBlock(
                            block_key="traceability",
                            content=[entry.model_dump(mode="json") for entry in traceability],
                            provenance="system_generated",
                        )
                    ],
                ),
                PERSection(
                    section_key="completeness_report",
                    title=_SECTION_TITLES["completeness_report"],
                    blocks=[
                        PERContentBlock(
                            block_key="completeness_gaps",
                            content=[gap.model_dump(mode="json") for gap in gaps],
                            provenance="system_generated",
                        )
                    ],
                ),
            ]
        )

        return PERReportPayload(
            report_type=report_type,
            product_uuid=product_uuid,
            product_version=product_item.version_no,
            baseline_uuid=baseline_uuid,
            sections=sections,
            traceability=traceability,
            completeness_gaps=gaps,
        )

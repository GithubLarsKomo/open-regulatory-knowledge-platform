"""Model-level regressions for governed PER payload integrity contracts."""

import hashlib

import pytest
from pydantic import ValidationError

from orkp.domain.per_completeness_models import PERCompletenessReport
from orkp.domain.per_draft_models import PERDraftPayload
from orkp.domain.per_report_object_models import (
    PERReportObjectPayload,
    canonicalize_per_draft,
)
from orkp.domain.per_section_coverage_models import (
    PERCanonicalSection,
    PERSectionCoverageReport,
    PERSectionCoverageSnapshotPayload,
)
from orkp.domain.performance_report_models import (
    PerformanceReportPayload,
    PerformanceReportSnapshot,
)


PRODUCT_UUID = "00000000000000000000000000000001"
COMPLETENESS_UUID = "00000000000000000000000000000002"
COVERAGE_UUID = "00000000000000000000000000000003"
BASELINE_UUID = "00000000000000000000000000000004"


def _product():
    return PerformanceReportSnapshot(
        object_uuid=PRODUCT_UUID,
        object_type="product",
        object_version=1,
        snapshot={"product_id": "P-INTEGRITY", "name": "Integrity Product"},
    )


def _performance_report():
    product = _product()
    return PerformanceReportPayload(
        baseline_uuid=BASELINE_UUID,
        baseline_name="Integrity baseline",
        product=product,
        sections=[],
    )


def _completeness():
    return PERCompletenessReport(
        snapshot_ref={"object_uuid": COMPLETENESS_UUID, "object_version": 1},
        gap_report={
            "product": {"object_uuid": PRODUCT_UUID, "object_version": 1},
            "performance_claim_count": 0,
            "sufficient_claim_count": 0,
            "gap_claim_count": 0,
            "complete": True,
            "claims": [],
        },
    )


def _sections():
    return [
        {
            "section_id": "cover_page",
            "status": "available",
            "source_refs": [{"object_uuid": PRODUCT_UUID, "object_version": 1}],
            "data": {"product": {"product_id": "P-INTEGRITY"}},
        },
        {
            "section_id": "intended_purpose",
            "status": "missing",
            "source_refs": [{"object_uuid": PRODUCT_UUID, "object_version": 1}],
            "gap_code": "PER-SECTION-INTENDED-PURPOSE-MISSING",
        },
        {
            "section_id": "scientific_validity",
            "status": "missing",
            "gap_code": "PER-SECTION-SCIENTIFIC-VALIDITY-MISSING",
        },
        {
            "section_id": "analytical_performance",
            "status": "missing",
            "gap_code": "PER-SECTION-ANALYTICAL-PERFORMANCE-MISSING",
        },
        {
            "section_id": "clinical_performance",
            "status": "missing",
            "gap_code": "PER-SECTION-CLINICAL-PERFORMANCE-MISSING",
        },
        {
            "section_id": "claims_and_evidence",
            "status": "missing",
            "gap_code": "PER-SECTION-CLAIMS-EVIDENCE-MISSING",
        },
        {
            "section_id": "risk_benefit_analysis",
            "status": "missing",
            "gap_code": "PER-SECTION-RISK-BENEFIT-MISSING",
        },
        {
            "section_id": "pmpf_summary",
            "status": "missing",
            "gap_code": "PER-SECTION-PMPF-MISSING",
        },
        {
            "section_id": "traceability_appendix",
            "status": "missing",
            "gap_code": "PER-SECTION-TRACEABILITY-MISSING",
        },
        {
            "section_id": "completeness_report",
            "status": "available",
            "source_refs": [{"object_uuid": COMPLETENESS_UUID, "object_version": 1}],
            "data": {"complete": True},
        },
    ]


def _coverage():
    return PERSectionCoverageReport(
        snapshot_ref={"object_uuid": COVERAGE_UUID, "object_version": 1},
        sections=_sections(),
    )


def _governed_draft():
    product = _product()
    return PERDraftPayload(
        schema_version="per-draft-1.3",
        baseline_uuid=BASELINE_UUID,
        baseline_name="Integrity baseline",
        product=product,
        performance_sections=_performance_report(),
        content_blocks=[],
        completeness_report=_completeness(),
        section_coverage=_coverage(),
        traceability_appendix=[],
    )


def _raw_draft():
    product = _product()
    return PERDraftPayload(
        schema_version="per-draft-1.1",
        baseline_uuid=BASELINE_UUID,
        baseline_name="Raw Performance baseline",
        product=product,
        performance_sections=_performance_report(),
        content_blocks=[],
        traceability_appendix=[],
    )


def test_draft_rejects_unsupported_schema_version():
    product = _product()
    with pytest.raises(ValidationError, match="Unsupported PER draft schema_version"):
        PERDraftPayload(
            schema_version="per-draft-1.2",
            baseline_uuid=BASELINE_UUID,
            baseline_name="Unsupported draft",
            product=product,
            performance_sections=_performance_report(),
            content_blocks=[],
            traceability_appendix=[],
        )


def test_governed_draft_requires_both_report_level_snapshots():
    product = _product()
    with pytest.raises(ValidationError, match="requires completeness"):
        PERDraftPayload(
            schema_version="per-draft-1.3",
            baseline_uuid=BASELINE_UUID,
            baseline_name="Incomplete governed draft",
            product=product,
            performance_sections=_performance_report(),
            content_blocks=[],
            completeness_report=_completeness(),
            traceability_appendix=[],
        )


def test_raw_draft_rejects_report_level_snapshots():
    product = _product()
    with pytest.raises(ValidationError, match="cannot contain report-level"):
        PERDraftPayload(
            schema_version="per-draft-1.1",
            baseline_uuid=BASELINE_UUID,
            baseline_name="Invalid raw draft",
            product=product,
            performance_sections=_performance_report(),
            content_blocks=[],
            completeness_report=_completeness(),
            section_coverage=_coverage(),
            traceability_appendix=[],
        )


def test_section_rejects_gap_code_from_another_section():
    with pytest.raises(ValidationError, match="requires gap_code"):
        PERCanonicalSection(
            section_id="risk_benefit_analysis",
            status="missing",
            gap_code="PER-SECTION-PMPF-MISSING",
        )


def test_available_section_requires_exact_source_reference():
    with pytest.raises(ValidationError, match="requires source_refs"):
        PERCanonicalSection(
            section_id="risk_benefit_analysis",
            status="available",
        )


def test_section_coverage_snapshot_rejects_unknown_schema_version():
    with pytest.raises(ValidationError, match="Unsupported PER section coverage"):
        PERSectionCoverageSnapshotPayload(
            schema_version="per-section-coverage-9.9",
            source_performance_baseline_uuid=BASELINE_UUID,
            sections=_sections(),
            owner_user_id="report-author",
        )


def test_persisted_report_rejects_raw_draft_even_with_matching_checksum():
    draft = _raw_draft()
    canonical = canonicalize_per_draft(draft)
    checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    with pytest.raises(ValidationError, match="requires governed per-draft-1.3"):
        PERReportObjectPayload(
            product={"object_uuid": PRODUCT_UUID, "object_version": 1},
            baseline_uuid=BASELINE_UUID,
            draft=draft,
            canonical_checksum_sha256=checksum,
        )


def test_persisted_report_rejects_unknown_object_schema_version():
    draft = _governed_draft()
    canonical = canonicalize_per_draft(draft)
    checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    with pytest.raises(ValidationError, match="Unsupported persisted PER report"):
        PERReportObjectPayload(
            schema_version="per-report-object-9.9",
            product={"object_uuid": PRODUCT_UUID, "object_version": 1},
            baseline_uuid=BASELINE_UUID,
            draft=draft,
            canonical_checksum_sha256=checksum,
        )

"""Regression tests for frozen canonical ten-section PER coverage."""

from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import BaselineValidationError
from orkp.domain.per_content_models import PERReportBaselineCreateRequest
from orkp.domain.per_draft_service import PERDraftService
from orkp.domain.per_report_baseline_service import PERReportBaselineService
from orkp.domain.per_section_coverage_models import PER_CANONICAL_SECTION_IDS
from orkp.domain.performance_models import PerformanceStudyCreateRequest
from orkp.domain.performance_report_models import PerformanceReportBaselineCreateRequest
from orkp.domain.performance_report_service import PerformanceReportService
from orkp.domain.performance_result_models import PerformanceResultCreateRequest
from orkp.domain.performance_result_service import PerformanceResultService
from orkp.domain.performance_service import PerformanceStudyService


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _approve(repo, obj, actor="approver"):
    repo.transition_state(obj.object_uuid, "in_review", "author")
    repo.transition_state(obj.object_uuid, "approved", actor)
    repo.session.commit()
    return obj


def _performance_context(repo, intended_purpose="Detection of analyte X"):
    product, _ = repo.create_object(
        "product",
        {
            "product_id": "P-SECTIONS",
            "name": "Section Coverage Product",
            "intended_purpose": intended_purpose,
        },
        "owner",
        "owner",
    )
    _approve(repo, product)
    claim, _ = repo.create_object(
        "claim",
        {
            "claim_type": "clinical",
            "claim_category": "clinical",
            "confidence": "high",
            "severity": "medium",
            "jurisdiction": "EU",
            "language": "en",
            "wording": "Clinical section claim",
            "regulatory_scope": [],
        },
        "claim-owner",
        "claim-owner",
    )
    _approve(repo, claim)
    repo.create_relation(
        source_uuid=product.object_uuid,
        source_version=1,
        target_uuid=claim.object_uuid,
        target_version=1,
        relation_type="has_claim",
        created_by="owner",
    )
    repo.session.commit()
    study = PerformanceStudyService(repo).create_study(
        product.uuid_hex,
        PerformanceStudyCreateRequest(
            study_id="ST-SECTIONS",
            study_type="clinical",
            title="Clinical section study",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            study_status="completed",
            owner_user_id="study-owner",
        ),
    )
    result = PerformanceResultService(repo).create_result(
        study.object_uuid,
        PerformanceResultCreateRequest(
            result_id="R-SECTIONS",
            study={"object_uuid": study.object_uuid, "object_version": 1},
            claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
            parameter="clinical sensitivity",
            result_value="99.8",
            interpretation="Frozen clinical interpretation.",
            quality_rating="high",
            owner_user_id="result-owner",
        ),
    )
    _approve(repo, repo.get_by_uuid_hex(result.object_uuid))
    baseline = PerformanceReportService(repo).create_baseline(
        PerformanceReportBaselineCreateRequest(
            name="Section source baseline",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            evidence=[{"object_uuid": result.object_uuid, "object_version": 1}],
            created_by_user_id="per-author",
        )
    )
    return product, claim, result, baseline


def _risk_context(repo, product):
    risk, _ = repo.create_object(
        "risk_analysis",
        {"risk_id": "RA-SECTIONS"},
        "risk-owner",
        "risk-owner",
    )
    repo.create_relation(
        source_uuid=risk.object_uuid,
        source_version=1,
        target_uuid=product.object_uuid,
        target_version=1,
        relation_type="applies_to_product",
        created_by="risk-owner",
    )
    policy, _ = repo.create_object(
        "risk_policy",
        {"policy_id": "RP-SECTIONS"},
        "risk-owner",
        "risk-owner",
    )
    residual, _ = repo.create_object(
        "residual_risk_evaluation",
        {
            "evaluation_id": "RRE-SECTIONS",
            "risk_analysis_uuid": risk.uuid_hex,
            "risk_analysis_version": 1,
            "initial_evaluation_uuid": risk.uuid_hex,
            "initial_evaluation_version": 1,
            "control_verifications": [
                {"object_uuid": risk.uuid_hex, "object_version": 1}
            ],
            "residual_severity": "moderate",
            "residual_probability": "possible",
            "calculated_risk_level": "high",
            "acceptable": False,
            "action_required": "benefit_risk_required",
            "severity_improved": False,
            "probability_improved": False,
            "severity_worsened": False,
            "probability_worsened": False,
            "risk_level_improved": False,
            "reduced": False,
            "regression_detected": False,
            "benefit_risk_required": True,
            "risk_policy_uuid": policy.uuid_hex,
            "risk_policy_version": 1,
            "policy_revision": "1.0",
            "evaluator_user_id": "risk-author",
            "rationale": "Residual risk requires benefit-risk analysis",
            "evaluated_at": "2026-08-11T00:00:00+00:00",
        },
        "risk-owner",
        "risk-owner",
    )
    repo.create_relation(
        source_uuid=residual.object_uuid,
        source_version=1,
        target_uuid=risk.object_uuid,
        target_version=1,
        relation_type="residual_of",
        created_by="risk-owner",
    )
    repo.create_relation(
        source_uuid=residual.object_uuid,
        source_version=1,
        target_uuid=policy.object_uuid,
        target_version=1,
        relation_type="uses_risk_policy",
        created_by="risk-owner",
    )
    benefit, _ = repo.create_object(
        "benefit_risk",
        {
            "analysis_id": "BR-SECTIONS",
            "residual_evaluation": {
                "object_uuid": residual.uuid_hex,
                "object_version": 1,
            },
            "risk_analysis": {"object_uuid": risk.uuid_hex, "object_version": 1},
            "risk_policy": {"object_uuid": policy.uuid_hex, "object_version": 1},
            "benefits": "Clinical benefit",
            "residual_risks": "Known residual risks",
            "rationale": "Benefit outweighs risk",
            "conclusion": "favorable",
            "evaluator_user_id": "risk-author",
            "evaluated_at": "2026-08-11T00:00:00+00:00",
        },
        "risk-author",
        "risk-author",
    )
    repo.create_relation(
        source_uuid=benefit.object_uuid,
        source_version=1,
        target_uuid=residual.object_uuid,
        target_version=1,
        relation_type="benefit_risk_for",
        created_by="risk-author",
    )
    repo.create_relation(
        source_uuid=benefit.object_uuid,
        source_version=1,
        target_uuid=policy.object_uuid,
        target_version=1,
        relation_type="uses_risk_policy",
        created_by="risk-author",
    )
    _approve(repo, benefit, actor="risk-approver")

    information, _ = repo.create_object(
        "post_market_information",
        {
            "information_id": "PMI-SECTIONS",
            "risk_analysis": {"object_uuid": risk.uuid_hex, "object_version": 1},
            "source_type": "pmpf",
            "title": "PMPF follow-up",
            "description": "PMPF source information",
            "observed_at": "2026-08-10",
            "reported_by_user_id": "pmpf-author",
            "received_at": "2026-08-11T00:00:00+00:00",
        },
        "pmpf-author",
        "pmpf-author",
    )
    repo.create_relation(
        source_uuid=information.object_uuid,
        source_version=1,
        target_uuid=risk.object_uuid,
        target_version=1,
        relation_type="impacts_risk",
        created_by="pmpf-author",
    )
    repo.create_relation(
        source_uuid=risk.object_uuid,
        source_version=1,
        target_uuid=information.object_uuid,
        target_version=1,
        relation_type="informed_by",
        created_by="pmpf-author",
    )
    assessment, _ = repo.create_object(
        "risk_impact_assessment",
        {
            "assessment_id": "RIA-SECTIONS",
            "risk_analysis": {"object_uuid": risk.uuid_hex, "object_version": 1},
            "post_market_information": {
                "object_uuid": information.uuid_hex,
                "object_version": 1,
            },
            "outcome": "no_change",
            "rationale": "No new risk signal",
            "requires_risk_review": False,
            "assessor_user_id": "pmpf-assessor",
            "assessed_at": "2026-08-11T00:00:00+00:00",
        },
        "pmpf-assessor",
        "pmpf-assessor",
    )
    repo.create_relation(
        source_uuid=assessment.object_uuid,
        source_version=1,
        target_uuid=information.object_uuid,
        target_version=1,
        relation_type="derived_from",
        created_by="pmpf-assessor",
        properties={"role": "impact_assessment_source"},
    )
    repo.create_relation(
        source_uuid=assessment.object_uuid,
        source_version=1,
        target_uuid=risk.object_uuid,
        target_version=1,
        relation_type="derived_from",
        created_by="pmpf-assessor",
        properties={"role": "assessed_risk"},
    )
    _approve(repo, assessment, actor="pmpf-approver")
    repo.session.commit()
    return risk, benefit, information, assessment


def _section(draft, section_id):
    assert draft.section_coverage is not None
    return next(
        section
        for section in draft.section_coverage.sections
        if section.section_id == section_id
    )


def test_report_baseline_freezes_exact_ten_sections_with_explicit_missing_gaps(repo):
    product, _, _, source = _performance_context(repo, intended_purpose="")

    report_baseline = PERReportBaselineService(repo).create_baseline(
        PERReportBaselineCreateRequest(
            name="Ten-section report baseline",
            performance_baseline_uuid=source.baseline_uuid,
            created_by_user_id="report-author",
        )
    )
    draft = PERDraftService(repo).build_draft(report_baseline.baseline_uuid)

    assert draft.schema_version == "per-draft-1.3"
    assert draft.section_coverage is not None
    assert [section.section_id for section in draft.section_coverage.sections] == list(
        PER_CANONICAL_SECTION_IDS
    )
    assert _section(draft, "cover_page").status == "available"
    assert _section(draft, "intended_purpose").gap_code == (
        "PER-SECTION-INTENDED-PURPOSE-MISSING"
    )
    assert _section(draft, "clinical_performance").status == "available"
    assert _section(draft, "scientific_validity").status == "missing"
    assert _section(draft, "risk_benefit_analysis").gap_code == (
        "PER-SECTION-RISK-BENEFIT-MISSING"
    )
    assert _section(draft, "pmpf_summary").gap_code == "PER-SECTION-PMPF-MISSING"
    assert report_baseline.section_coverage_snapshot_ref.object_version == 1
    items = repo.list_baseline_items(UUID(report_baseline.baseline_uuid).bytes)
    assert len([i for i in items if i.object_type == "report_section_coverage"]) == 1
    assert _section(draft, "cover_page").source_refs[0].object_uuid == product.uuid_hex


def test_explicit_approved_risk_benefit_and_pmpf_sources_are_frozen(repo):
    product, _, _, source = _performance_context(repo)
    risk, benefit, information, assessment = _risk_context(repo, product)

    report_baseline = PERReportBaselineService(repo).create_baseline(
        PERReportBaselineCreateRequest(
            name="Cross-domain section baseline",
            performance_baseline_uuid=source.baseline_uuid,
            benefit_risk_sources=[
                {"object_uuid": benefit.uuid_hex, "object_version": 1}
            ],
            pmpf_assessments=[
                {"object_uuid": assessment.uuid_hex, "object_version": 1}
            ],
            created_by_user_id="report-author",
        )
    )
    draft = PERDraftService(repo).build_draft(report_baseline.baseline_uuid)

    risk_section = _section(draft, "risk_benefit_analysis")
    pmpf_section = _section(draft, "pmpf_summary")
    assert risk_section.status == "available"
    assert pmpf_section.status == "available"
    assert benefit.uuid_hex in {ref.object_uuid for ref in risk_section.source_refs}
    assert assessment.uuid_hex in {ref.object_uuid for ref in pmpf_section.source_refs}
    assert information.uuid_hex in {ref.object_uuid for ref in pmpf_section.source_refs}
    items = repo.list_baseline_items(UUID(report_baseline.baseline_uuid).bytes)
    frozen = {(UUID(bytes=item.object_uuid).hex, item.version_no) for item in items}
    assert (risk.uuid_hex, 1) in frozen
    assert (benefit.uuid_hex, 1) in frozen
    assert (information.uuid_hex, 1) in frozen
    assert (assessment.uuid_hex, 1) in frozen


def test_cross_domain_risk_source_for_other_product_is_rejected(repo):
    product, _, _, source = _performance_context(repo)
    other, _ = repo.create_object(
        "product",
        {"product_id": "P-OTHER", "name": "Other"},
        "owner",
        "owner",
    )
    repo.session.commit()
    _, benefit, _, _ = _risk_context(repo, other)

    with pytest.raises(
        BaselineValidationError, match="not pinned to the frozen Product"
    ):
        PERReportBaselineService(repo).create_baseline(
            PERReportBaselineCreateRequest(
                name="Wrong Product risk source",
                performance_baseline_uuid=source.baseline_uuid,
                benefit_risk_sources=[
                    {"object_uuid": benefit.uuid_hex, "object_version": 1}
                ],
                created_by_user_id="report-author",
            )
        )

    assert repo.list_objects(object_type="report_section_coverage") == []


def test_non_pmpf_information_is_rejected(repo):
    product, _, _, source = _performance_context(repo)
    risk, _, information, assessment = _risk_context(repo, product)
    info = repo.get_by_uuid_hex(information.uuid_hex)
    payload = dict(repo.get_version(info.object_uuid, 1).payload_json)
    payload["source_type"] = "complaint"
    repo.create_version(info.object_uuid, payload, "pmpf-author")
    assessment_obj = repo.get_by_uuid_hex(assessment.uuid_hex)
    assessment2, _ = repo.create_object(
        "risk_impact_assessment",
        {
            **repo.get_version(assessment_obj.object_uuid, 1).payload_json,
            "assessment_id": "RIA-NON-PMPF",
            "post_market_information": {
                "object_uuid": information.uuid_hex,
                "object_version": 2,
            },
        },
        "pmpf-assessor-2",
        "pmpf-assessor-2",
    )
    repo.create_relation(
        source_uuid=assessment2.object_uuid,
        source_version=1,
        target_uuid=information.object_uuid,
        target_version=2,
        relation_type="derived_from",
        created_by="pmpf-assessor-2",
        properties={"role": "impact_assessment_source"},
    )
    repo.create_relation(
        source_uuid=assessment2.object_uuid,
        source_version=1,
        target_uuid=risk.object_uuid,
        target_version=1,
        relation_type="derived_from",
        created_by="pmpf-assessor-2",
        properties={"role": "assessed_risk"},
    )
    repo.create_relation(
        source_uuid=information.object_uuid,
        source_version=2,
        target_uuid=risk.object_uuid,
        target_version=1,
        relation_type="impacts_risk",
        created_by="pmpf-author",
    )
    repo.create_relation(
        source_uuid=risk.object_uuid,
        source_version=1,
        target_uuid=information.object_uuid,
        target_version=2,
        relation_type="informed_by",
        created_by="pmpf-author",
    )
    _approve(repo, assessment2, actor="pmpf-approver-2")

    with pytest.raises(BaselineValidationError, match="source_type='pmpf'"):
        PERReportBaselineService(repo).create_baseline(
            PERReportBaselineCreateRequest(
                name="Non-PMPF source",
                performance_baseline_uuid=source.baseline_uuid,
                pmpf_assessments=[
                    {"object_uuid": assessment2.uuid_hex, "object_version": 1}
                ],
                created_by_user_id="report-author",
            )
        )


def test_section_coverage_is_frozen_after_live_snapshot_object_changes(repo):
    _, _, _, source = _performance_context(repo)
    report_baseline = PERReportBaselineService(repo).create_baseline(
        PERReportBaselineCreateRequest(
            name="Frozen section coverage",
            performance_baseline_uuid=source.baseline_uuid,
            created_by_user_id="report-author",
        )
    )
    service = PERDraftService(repo)
    first = service.build_draft(report_baseline.baseline_uuid)

    items = repo.list_baseline_items(UUID(report_baseline.baseline_uuid).bytes)
    coverage_item = next(
        item for item in items if item.object_type == "report_section_coverage"
    )
    coverage_object = repo.get_by_uuid(coverage_item.object_uuid)
    changed = dict(coverage_item.snapshot_json)
    changed["owner_user_id"] = "later-author"
    repo.create_version(coverage_object.object_uuid, changed, "later-author")
    repo.session.commit()

    second = service.build_draft(report_baseline.baseline_uuid)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.section_coverage is not None
    assert first.section_coverage.snapshot_ref.object_version == 1


def test_generator_rejects_duplicate_section_coverage_snapshots(repo):
    _, _, _, source = _performance_context(repo)
    report_baseline = PERReportBaselineService(repo).create_baseline(
        PERReportBaselineCreateRequest(
            name="Duplicate section coverage source",
            performance_baseline_uuid=source.baseline_uuid,
            created_by_user_id="report-author",
        )
    )
    items = repo.list_baseline_items(UUID(report_baseline.baseline_uuid).bytes)
    coverage = next(
        item for item in items if item.object_type == "report_section_coverage"
    )
    duplicate, _ = repo.create_object(
        "report_section_coverage",
        dict(coverage.snapshot_json),
        "report-author",
        "report-author",
    )
    versions = [(item.object_uuid, item.version_no) for item in items]
    versions.append((duplicate.object_uuid, 1))
    tampered = repo.create_baseline(
        "Duplicate section coverage",
        None,
        versions,
        "report-author",
    )
    repo.session.commit()

    with pytest.raises(BaselineValidationError, match="exactly one section coverage"):
        PERDraftService(repo).build_draft(UUID(bytes=tampered.baseline_uuid).hex)

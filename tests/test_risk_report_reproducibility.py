"""Regression tests for reproducible Risk reports from frozen baselines."""

import hashlib
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from orkp.db.models import Base, GeneratedArtifact
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import BaselineValidationError
from orkp.domain.risk_report_models import RiskReportBaselineCreateRequest
from orkp.domain.risk_report_service import RiskReportService


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _approved_risk(repo):
    risk, _ = repo.create_object(
        "risk_analysis",
        {"risk_id": "R-RMR", "title": "Approved report risk"},
        "risk-author",
        "risk-author",
    )
    repo.transition_state(risk.object_uuid, "in_review", "risk-author")
    repo.transition_state(risk.object_uuid, "approved", "risk-approver")
    repo.session.commit()
    return risk


def _support(repo, object_type="hazard", payload=None):
    support, _ = repo.create_object(
        object_type,
        payload or {"id": f"{object_type}-1", "description": "Frozen support"},
        "risk-author",
        "risk-author",
    )
    repo.session.commit()
    return support


def _request(risk, *supports):
    objects = [
        {"object_uuid": risk.uuid_hex, "object_version": risk.current_version},
    ]
    objects.extend(
        {"object_uuid": support.uuid_hex, "object_version": support.current_version}
        for support in supports
    )
    return RiskReportBaselineCreateRequest(
        name="Risk Management Report baseline",
        description="Frozen inputs for reproducible Risk report generation.",
        objects=objects,
        created_by_user_id="report-author",
    )


def test_baseline_requires_approved_or_effective_risk_root(repo):
    risk, _ = repo.create_object(
        "risk_analysis",
        {"risk_id": "R-DRAFT"},
        "risk-author",
        "risk-author",
    )
    repo.session.commit()

    with pytest.raises(BaselineValidationError):
        RiskReportService(repo).create_baseline(_request(risk))


def test_baseline_requires_at_least_one_risk_root(repo):
    hazard = _support(repo)
    request = RiskReportBaselineCreateRequest(
        name="Invalid baseline",
        objects=[{"object_uuid": hazard.uuid_hex, "object_version": 1}],
        created_by_user_id="report-author",
    )

    with pytest.raises(BaselineValidationError):
        RiskReportService(repo).create_baseline(request)


def test_baseline_rejects_stale_risk_analysis_version(repo):
    risk, _ = repo.create_object(
        "risk_analysis",
        {"risk_id": "R-STALE", "title": "v1"},
        "risk-author",
        "risk-author",
    )
    repo.create_version(
        risk.object_uuid,
        {"risk_id": "R-STALE", "title": "v2"},
        "risk-author",
    )
    repo.transition_state(risk.object_uuid, "in_review", "risk-author")
    repo.transition_state(risk.object_uuid, "approved", "risk-approver")
    repo.session.commit()
    request = RiskReportBaselineCreateRequest(
        name="Stale baseline",
        objects=[{"object_uuid": risk.uuid_hex, "object_version": 1}],
        created_by_user_id="report-author",
    )

    with pytest.raises(BaselineValidationError):
        RiskReportService(repo).create_baseline(request)


def test_baseline_rejects_duplicate_object_version_reference(repo):
    risk = _approved_risk(repo)
    reference = {"object_uuid": risk.uuid_hex, "object_version": 1}
    request = RiskReportBaselineCreateRequest(
        name="Duplicate baseline",
        objects=[reference, reference],
        created_by_user_id="report-author",
    )

    with pytest.raises(BaselineValidationError):
        RiskReportService(repo).create_baseline(request)


def test_supporting_draft_versions_are_frozen_with_approved_risk_root(repo):
    risk = _approved_risk(repo)
    hazard = _support(repo)

    baseline = RiskReportService(repo).create_baseline(_request(risk, hazard))
    items = repo.list_baseline_items(UUID(baseline.baseline_uuid).bytes)

    assert baseline.item_count == 2
    snapshots = {
        (item.object_type, item.version_no): item.snapshot_json for item in items
    }
    assert snapshots[("risk_analysis", 1)]["risk_id"] == "R-RMR"
    assert snapshots[("hazard", 1)]["description"] == "Frozen support"


def test_report_is_stable_when_supporting_source_gets_new_version(repo):
    risk = _approved_risk(repo)
    hazard = _support(repo)
    service = RiskReportService(repo)
    baseline = service.create_baseline(_request(risk, hazard))

    first = service.generate_report(baseline.baseline_uuid, "report-generator")

    repo.create_version(
        hazard.object_uuid,
        {"id": "hazard-1", "description": "Changed after baseline freeze"},
        "risk-author",
    )
    repo.session.commit()

    second = service.generate_report(baseline.baseline_uuid, "report-generator")

    assert first.canonical_json == second.canonical_json
    assert first.checksum_sha256 == second.checksum_sha256
    assert first.artifact_uuid != second.artifact_uuid
    assert "Changed after baseline freeze" not in second.canonical_json
    assert "Frozen support" in second.canonical_json


def test_report_checksum_matches_canonical_bytes_and_artifacts_link_to_baseline(repo):
    risk = _approved_risk(repo)
    hazard = _support(repo)
    control = _support(
        repo,
        "risk_control",
        {"control_id": "RC-1", "description": "Control snapshot"},
    )
    service = RiskReportService(repo)
    baseline = service.create_baseline(_request(risk, control, hazard))

    result = service.generate_report(baseline.baseline_uuid, "report-generator")

    assert result.checksum_sha256 == hashlib.sha256(
        result.canonical_json.encode("utf-8")
    ).hexdigest()
    assert [item.object_type for item in result.report.items] == [
        "hazard",
        "risk_analysis",
        "risk_control",
    ]

    artifacts = list(repo.session.execute(select(GeneratedArtifact)).scalars().all())
    assert len(artifacts) == 1
    assert artifacts[0].baseline_uuid == UUID(baseline.baseline_uuid).bytes
    assert artifacts[0].artifact_type == "risk_management_report"
    assert artifacts[0].format == "json"
    assert artifacts[0].checksum == result.checksum_sha256


def test_risk_lifecycle_change_after_freeze_does_not_change_report(repo):
    risk = _approved_risk(repo)
    service = RiskReportService(repo)
    baseline = service.create_baseline(_request(risk))
    first = service.generate_report(baseline.baseline_uuid, "report-generator")

    repo.transition_state(risk.object_uuid, "effective", "risk-approver")
    repo.session.commit()

    second = service.generate_report(baseline.baseline_uuid, "report-generator")
    assert first.canonical_json == second.canonical_json
    assert first.checksum_sha256 == second.checksum_sha256

"""Regression tests for exact Performance Result graph revalidation at PER freeze."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import BaselineValidationError
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


def _approve(repo, obj):
    repo.transition_state(obj.object_uuid, "in_review", "author")
    repo.transition_state(obj.object_uuid, "approved", "approver")
    repo.session.commit()
    return obj


def _context(repo):
    product, _ = repo.create_object("product", {"id": "P-GATE"}, "owner", "owner")
    _approve(repo, product)
    claim, _ = repo.create_object("claim", {"id": "C-GATE"}, "owner", "owner")
    _approve(repo, claim)
    study = PerformanceStudyService(repo).create_study(
        product.uuid_hex,
        PerformanceStudyCreateRequest(
            study_id="ST-GATE",
            study_type="analytical",
            title="Gate study",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            study_status="completed",
            owner_user_id="study-owner",
        ),
    )
    request = PerformanceResultCreateRequest(
        result_id="R-GATE",
        study={"object_uuid": study.object_uuid, "object_version": 1},
        claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
        parameter="specificity",
        result_value="99.0",
        quality_rating="high",
        owner_user_id="result-owner",
    )
    return product, claim, study, request


def _baseline_request(product, result_uuid: str, version: int):
    return PerformanceReportBaselineCreateRequest(
        name="Traceability gate baseline",
        product={"object_uuid": product.uuid_hex, "object_version": 1},
        evidence=[{"object_uuid": result_uuid, "object_version": version}],
        created_by_user_id="per-author",
    )


def test_per_baseline_rejects_forged_result_payload_without_graph(repo):
    product, _, study, request = _context(repo)
    legitimate = PerformanceResultService(repo).create_result(study.object_uuid, request)
    payload = legitimate.payload.model_dump()

    forged, _ = repo.create_object("evidence", payload, "result-owner", "result-owner")
    _approve(repo, forged)

    with pytest.raises(BaselineValidationError, match="Result to Study provenance"):
        PerformanceReportService(repo).create_baseline(
            _baseline_request(product, forged.uuid_hex, 1)
        )


def test_per_baseline_rejects_new_result_version_with_only_old_relations(repo):
    product, _, study, request = _context(repo)
    legitimate = PerformanceResultService(repo).create_result(study.object_uuid, request)
    result = repo.get_by_uuid_hex(legitimate.object_uuid)
    repo.create_version(result.object_uuid, legitimate.payload.model_dump(), "result-owner")
    _approve(repo, result)

    with pytest.raises(BaselineValidationError, match="Result to Study provenance"):
        PerformanceReportService(repo).create_baseline(
            _baseline_request(product, result.uuid_hex, 2)
        )

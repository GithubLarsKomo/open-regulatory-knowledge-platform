"""Regression tests for statistical Performance Result provenance."""

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import InvalidRelationError
from orkp.domain.performance_models import PerformanceStudyCreateRequest
from orkp.domain.performance_result_models import PerformanceResultCreateRequest
from orkp.domain.performance_result_service import PerformanceResultService
from orkp.domain.performance_service import PerformanceStudyService


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _create_object(repo, object_type: str, payload: dict):
    obj, _ = repo.create_object(object_type, payload, "owner", "owner")
    repo.session.commit()
    return obj


def _study_and_claim(repo):
    product = _create_object(repo, "product", {"id": "P-STATS"})
    study = PerformanceStudyService(repo).create_study(
        product.uuid_hex,
        PerformanceStudyCreateRequest(
            study_id="ST-STATS",
            study_type="analytical",
            title="Analytical performance study",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            study_status="completed",
            owner_user_id="study-owner",
        ),
    )
    claim = _create_object(repo, "claim", {"id": "C-STATS"})
    return study, claim


def _source(repo, evidence_type: str, title: str):
    return _create_object(
        repo,
        "evidence",
        {"evidence_type": evidence_type, "title": title},
    )


def _approve(repo, evidence):
    repo.transition_state(evidence.object_uuid, "in_review", "reviewer")
    repo.transition_state(evidence.object_uuid, "approved", "approver")
    repo.session.commit()
    return repo.get_by_uuid(evidence.object_uuid)


def _request(study, claim, sources):
    return PerformanceResultCreateRequest(
        result_id="PR-STATS-001",
        study={"object_uuid": study.object_uuid, "object_version": 1},
        claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
        parameter="sensitivity",
        result_value="98.7",
        unit="%",
        statistical_method="Wilson 95% CI",
        statistical_sources=sources,
        interpretation="Meets acceptance criterion",
        quality_rating="high",
        owner_user_id="result-owner",
    )


def _ref(source, source_kind: str):
    return {
        "source_kind": source_kind,
        "evidence": {
            "object_uuid": source.uuid_hex,
            "object_version": source.current_version,
        },
    }


def test_statistical_method_requires_statistical_source(repo):
    study, claim = _study_and_claim(repo)

    with pytest.raises(ValidationError, match="statistical_sources are required"):
        _request(study, claim, [])


def test_duplicate_statistical_sources_are_rejected(repo):
    study, claim = _study_and_claim(repo)
    source = _source(repo, "internal_document", "Raw dataset")

    with pytest.raises(ValidationError, match="statistical_sources must not contain duplicates"):
        _request(study, claim, [_ref(source, "source_data"), _ref(source, "source_data")])


def test_source_data_persists_exact_provenance_relation(repo):
    study, claim = _study_and_claim(repo)
    source = _source(repo, "internal_document", "Locked raw dataset")

    result = PerformanceResultService(repo).create_result(
        study.object_uuid,
        _request(study, claim, [_ref(source, "source_data")]),
    )
    result_obj = repo.get_by_uuid_hex(result.object_uuid)
    relations = repo.list_active_relations_for_source(result_obj.object_uuid)
    source_relations = [
        relation
        for relation in relations
        if relation.relation_type == "derived_from"
        and relation.properties == {"role": "statistical_source_data"}
    ]

    assert len(source_relations) == 1
    assert source_relations[0].source_version == 1
    assert source_relations[0].target_uuid == source.object_uuid
    assert source_relations[0].target_version == 1


def test_source_data_rejects_non_document_evidence(repo):
    study, claim = _study_and_claim(repo)
    source = _source(repo, "internal_report", "Not raw data")

    with pytest.raises(InvalidRelationError, match="internal_document"):
        PerformanceResultService(repo).create_result(
            study.object_uuid,
            _request(study, claim, [_ref(source, "source_data")]),
        )


def test_validated_report_requires_report_evidence_type(repo):
    study, claim = _study_and_claim(repo)
    source = _approve(repo, _source(repo, "internal_document", "Approved document"))

    with pytest.raises(InvalidRelationError, match="internal_report or external_report"):
        PerformanceResultService(repo).create_result(
            study.object_uuid,
            _request(study, claim, [_ref(source, "validated_report")]),
        )


def test_validated_report_requires_approved_lifecycle(repo):
    study, claim = _study_and_claim(repo)
    source = _source(repo, "internal_report", "Draft study report")

    with pytest.raises(InvalidRelationError, match="approved or effective"):
        PerformanceResultService(repo).create_result(
            study.object_uuid,
            _request(study, claim, [_ref(source, "validated_report")]),
        )


def test_approved_validated_report_is_version_pinned(repo):
    study, claim = _study_and_claim(repo)
    source = _approve(repo, _source(repo, "external_report", "Validated study report"))

    result = PerformanceResultService(repo).create_result(
        study.object_uuid,
        _request(study, claim, [_ref(source, "validated_report")]),
    )
    result_obj = repo.get_by_uuid_hex(result.object_uuid)
    relations = repo.list_active_relations_for_source(result_obj.object_uuid)
    report_relations = [
        relation
        for relation in relations
        if relation.relation_type == "derived_from"
        and relation.properties == {"role": "validated_study_report"}
    ]

    assert len(report_relations) == 1
    assert report_relations[0].target_uuid == source.object_uuid
    assert report_relations[0].target_version == 1


def test_stale_statistical_source_version_is_rejected(repo):
    study, claim = _study_and_claim(repo)
    source = _source(repo, "internal_document", "Raw dataset")
    request = _request(study, claim, [_ref(source, "source_data")])
    repo.create_version(
        source.object_uuid,
        {"evidence_type": "internal_document", "title": "Raw dataset v2"},
        "owner",
    )
    repo.session.commit()

    with pytest.raises(InvalidRelationError, match="current statistical source versions"):
        PerformanceResultService(repo).create_result(study.object_uuid, request)


def test_historical_result_keeps_statistical_source_snapshot(repo):
    study, claim = _study_and_claim(repo)
    source = _source(repo, "internal_document", "Raw dataset")
    service = PerformanceResultService(repo)
    result = service.create_result(
        study.object_uuid,
        _request(study, claim, [_ref(source, "source_data")]),
    )

    repo.create_version(
        source.object_uuid,
        {"evidence_type": "internal_document", "title": "Later dataset"},
        "owner",
    )
    repo.session.commit()

    loaded = service.get_result(result.object_uuid, 1)
    assert loaded.payload.statistical_sources[0].evidence.object_version == 1
    result_obj = repo.get_by_uuid_hex(result.object_uuid)
    relation = next(
        relation
        for relation in repo.list_active_relations_for_source(result_obj.object_uuid)
        if relation.properties == {"role": "statistical_source_data"}
    )
    assert relation.target_version == 1

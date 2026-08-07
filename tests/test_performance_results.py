"""Regression tests for Performance Result to Claim traceability."""

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import InvalidRelationError, ObjectTypeMismatchError
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


def _create_study(repo, study_type="analytical"):
    product = _create_object(repo, "product", {"id": "P-PERF"})
    request = PerformanceStudyCreateRequest(
        study_id=f"ST-{study_type}",
        study_type=study_type,
        title="Performance study",
        product={"object_uuid": product.uuid_hex, "object_version": 1},
        study_status="completed",
        owner_user_id="study-owner",
    )
    return PerformanceStudyService(repo).create_study(product.uuid_hex, request)


def _create_claim(repo, identifier: str):
    return _create_object(repo, "claim", {"id": identifier})


def _request(study, *claims):
    return PerformanceResultCreateRequest(
        result_id="PR-001",
        study={
            "object_uuid": study.object_uuid,
            "object_version": study.object_version,
        },
        claims=[
            {"object_uuid": claim.uuid_hex, "object_version": claim.current_version}
            for claim in claims
        ],
        parameter="sensitivity",
        result_value="98.7",
        unit="%",
        statistical_method="Wilson 95% CI",
        interpretation="Meets predefined acceptance criterion",
        quality_rating="high",
        owner_user_id="result-owner",
    )


@pytest.mark.parametrize(
    ("study_type", "expected_evidence_type"),
    [
        ("analytical", "analytical_study"),
        ("clinical", "clinical_study"),
        ("scientific_validity", "scientific_validity"),
    ],
)
def test_result_evidence_type_is_derived_from_study_category(
    repo, study_type, expected_evidence_type
):
    study = _create_study(repo, study_type)
    claim = _create_claim(repo, f"C-{study_type}")

    result = PerformanceResultService(repo).create_result(
        study.object_uuid, _request(study, claim)
    )

    assert result.payload.evidence_type == expected_evidence_type
    stored = repo.get_by_uuid_hex(result.object_uuid)
    assert stored.object_type == "evidence"


def test_result_persists_exact_study_and_multi_claim_relations(repo):
    study = _create_study(repo)
    claim_a = _create_claim(repo, "C-A")
    claim_b = _create_claim(repo, "C-B")

    result = PerformanceResultService(repo).create_result(
        study.object_uuid, _request(study, claim_a, claim_b)
    )
    stored = repo.get_by_uuid_hex(result.object_uuid)
    relations = repo.list_active_relations_for_source(stored.object_uuid)

    derived = [
        relation for relation in relations if relation.relation_type == "derived_from"
    ]
    supported = [
        relation for relation in relations if relation.relation_type == "supported_by"
    ]

    assert len(derived) == 1
    assert derived[0].source_version == 1
    assert derived[0].target_version == study.object_version
    assert derived[0].properties == {"role": "performance_result_source"}
    assert len(supported) == 2
    assert {relation.target_uuid for relation in supported} == {
        claim_a.object_uuid,
        claim_b.object_uuid,
    }
    assert all(relation.source_version == 1 for relation in supported)
    assert all(relation.target_version == 1 for relation in supported)


def test_result_rejects_duplicate_claim_references(repo):
    study = _create_study(repo)
    claim = _create_claim(repo, "C-DUP")

    with pytest.raises(ValidationError, match="claims must not contain duplicates"):
        _request(study, claim, claim)


def test_result_rejects_stale_study_version(repo):
    study = _create_study(repo)
    claim = _create_claim(repo, "C-STALE-STUDY")
    study_obj = repo.get_by_uuid_hex(study.object_uuid)
    repo.create_version(
        study_obj.object_uuid,
        {**study.payload.model_dump(), "title": "Study v2"},
        "study-owner",
    )
    repo.session.commit()

    with pytest.raises(InvalidRelationError, match="current Study version"):
        PerformanceResultService(repo).create_result(
            study.object_uuid, _request(study, claim)
        )


def test_result_rejects_stale_claim_version(repo):
    study = _create_study(repo)
    claim = _create_claim(repo, "C-STALE-CLAIM")
    request = _request(study, claim)
    repo.create_version(claim.object_uuid, {"id": "C-STALE-CLAIM-v2"}, "owner")
    repo.session.commit()

    with pytest.raises(InvalidRelationError, match="current Claim versions"):
        PerformanceResultService(repo).create_result(study.object_uuid, request)


def test_result_rejects_non_claim_reference(repo):
    study = _create_study(repo)
    product = _create_object(repo, "product", {"id": "NOT-CLAIM"})

    with pytest.raises(ObjectTypeMismatchError):
        PerformanceResultService(repo).create_result(
            study.object_uuid, _request(study, product)
        )


def test_historical_result_remains_readable_after_source_versions_change(repo):
    study = _create_study(repo)
    claim = _create_claim(repo, "C-HISTORY")
    service = PerformanceResultService(repo)
    result = service.create_result(study.object_uuid, _request(study, claim))

    study_obj = repo.get_by_uuid_hex(study.object_uuid)
    repo.create_version(
        study_obj.object_uuid,
        {**study.payload.model_dump(), "title": "Later Study version"},
        "study-owner",
    )
    repo.create_version(claim.object_uuid, {"id": "C-HISTORY-v2"}, "owner")
    repo.session.commit()

    loaded = service.get_result(result.object_uuid, 1)
    assert loaded == result

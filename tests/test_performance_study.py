"""Regression tests for the structured Performance Study core."""

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import InvalidRelationError, ObjectTypeMismatchError
from orkp.domain.performance_models import PerformanceStudyCreateRequest
from orkp.domain.performance_service import PerformanceStudyService


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _product(repo):
    product, _ = repo.create_object(
        "product",
        {"product_id": "P-PERF", "name": "Performance product"},
        "product-owner",
        "product-owner",
    )
    repo.session.commit()
    return product


def _request(product, study_type="analytical", **overrides):
    data = {
        "study_id": f"ST-{study_type}",
        "study_type": study_type,
        "title": f"{study_type} study",
        "description": "Structured performance study",
        "product": {
            "object_uuid": product.uuid_hex,
            "object_version": product.current_version,
        },
        "study_status": "planned",
        "owner_user_id": "study-owner",
    }
    data.update(overrides)
    return PerformanceStudyCreateRequest(**data)


@pytest.mark.parametrize(
    "study_type",
    ["analytical", "clinical", "scientific_validity"],
)
def test_create_study_distinguishes_performance_categories(repo, study_type):
    product = _product(repo)

    created = PerformanceStudyService(repo).create_study(
        product.uuid_hex,
        _request(product, study_type),
    )

    stored = repo.get_by_uuid_hex(created.object_uuid)
    assert stored is not None
    assert stored.object_type == "study"
    assert created.object_version == 1
    assert created.lifecycle_state == "draft"
    assert created.payload.study_type == study_type
    assert created.payload.product.object_uuid == product.uuid_hex
    assert created.payload.product.object_version == 1


def test_study_model_rejects_unknown_fields_and_invalid_enums(repo):
    product = _product(repo)
    base = _request(product).model_dump()

    with pytest.raises(ValidationError):
        PerformanceStudyCreateRequest(**{**base, "study_type": "other"})
    with pytest.raises(ValidationError):
        PerformanceStudyCreateRequest(**{**base, "study_status": "published"})
    with pytest.raises(ValidationError):
        PerformanceStudyCreateRequest(**{**base, "unexpected": True})


def test_create_study_rejects_non_product_reference(repo):
    claim, _ = repo.create_object(
        "claim",
        {"claim_id": "C-PERF"},
        "claim-owner",
        "claim-owner",
    )
    repo.session.commit()
    request = PerformanceStudyCreateRequest(
        study_id="ST-WRONG-TYPE",
        study_type="clinical",
        title="Wrong target",
        product={"object_uuid": claim.uuid_hex, "object_version": 1},
        owner_user_id="study-owner",
    )

    with pytest.raises(ObjectTypeMismatchError):
        PerformanceStudyService(repo).create_study(claim.uuid_hex, request)


def test_create_study_rejects_path_reference_mismatch(repo):
    product = _product(repo)
    other, _ = repo.create_object(
        "product",
        {"product_id": "P-OTHER"},
        "product-owner",
        "product-owner",
    )
    repo.session.commit()

    with pytest.raises(InvalidRelationError, match="Path Product UUID"):
        PerformanceStudyService(repo).create_study(
            product.uuid_hex,
            _request(other),
        )


def test_create_study_rejects_stale_product_version(repo):
    product = _product(repo)
    repo.create_version(
        product.object_uuid,
        {"product_id": "P-PERF", "name": "Performance product v2"},
        "product-owner",
    )
    repo.session.commit()
    request = PerformanceStudyCreateRequest(
        study_id="ST-STALE",
        study_type="analytical",
        title="Stale product study",
        product={"object_uuid": product.uuid_hex, "object_version": 1},
        owner_user_id="study-owner",
    )

    with pytest.raises(InvalidRelationError, match="current Product version"):
        PerformanceStudyService(repo).create_study(product.uuid_hex, request)


def test_exact_study_version_remains_readable_after_product_changes(repo):
    product = _product(repo)
    service = PerformanceStudyService(repo)
    created = service.create_study(product.uuid_hex, _request(product, "clinical"))

    repo.create_version(
        product.object_uuid,
        {"product_id": "P-PERF", "name": "Performance product v2"},
        "product-owner",
    )
    repo.session.commit()

    loaded = service.get_study(created.object_uuid, 1)
    assert loaded.payload.product.object_uuid == product.uuid_hex
    assert loaded.payload.product.object_version == 1
    assert loaded.payload.study_type == "clinical"

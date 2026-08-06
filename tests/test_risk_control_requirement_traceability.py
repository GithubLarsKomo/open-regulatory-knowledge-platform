"""Regression tests for Risk Control to Requirement traceability."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import ObjectTypeMismatchError
from orkp.domain.risk_control_requirement_service import (
    RiskControlRequirementService,
)
from orkp.domain.risk_service import RiskService


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _object(repo, object_type: str, identifier: str):
    obj, _ = repo.create_object(
        object_type,
        {"id": identifier},
        "owner",
        "owner",
    )
    repo.session.commit()
    return obj


def test_link_requirement_pins_current_control_and_requirement_versions(repo):
    control = _object(repo, "risk_control", "RC-001")
    requirement = _object(repo, "requirement", "REQ-001")

    result = RiskControlRequirementService(repo).link_requirement(
        control.uuid_hex,
        requirement.uuid_hex,
        "risk-owner",
    )

    assert result.risk_control.object_uuid == control.uuid_hex
    assert result.risk_control.object_version == 1
    assert result.requirement.object_uuid == requirement.uuid_hex
    assert result.requirement.object_version == 1
    assert result.relation_type == "implements_requirement"

    relation = next(
        relation
        for relation in repo.list_active_relations_for_source(control.object_uuid)
        if relation.relation_type == "implements_requirement"
    )
    assert relation.source_version == 1
    assert relation.target_uuid == requirement.object_uuid
    assert relation.target_version == 1


def test_link_requirement_rejects_wrong_target_type(repo):
    control = _object(repo, "risk_control", "RC-001")
    not_requirement = _object(repo, "claim", "CLM-001")

    with pytest.raises(ObjectTypeMismatchError):
        RiskControlRequirementService(repo).link_requirement(
            control.uuid_hex,
            not_requirement.uuid_hex,
            "risk-owner",
        )


def test_requirement_version_change_does_not_rewrite_historical_relation(repo):
    control = _object(repo, "risk_control", "RC-001")
    requirement = _object(repo, "requirement", "REQ-001")
    RiskControlRequirementService(repo).link_requirement(
        control.uuid_hex,
        requirement.uuid_hex,
        "risk-owner",
    )

    repo.create_version(
        requirement.object_uuid,
        {"id": "REQ-001", "revision": "B"},
        "requirements-owner",
    )
    repo.session.commit()

    relation = next(
        relation
        for relation in repo.list_active_relations_for_source(control.object_uuid)
        if relation.relation_type == "implements_requirement"
    )
    assert requirement.current_version == 2
    assert relation.target_version == 1


def test_risk_traceability_includes_control_requirement_edge(repo):
    risk = _object(repo, "risk_analysis", "RA-001")
    control = _object(repo, "risk_control", "RC-001")
    requirement = _object(repo, "requirement", "REQ-001")

    repo.create_relation(
        source_uuid=risk.object_uuid,
        source_version=risk.current_version,
        target_uuid=control.object_uuid,
        target_version=control.current_version,
        relation_type="controlled_by",
        created_by="risk-owner",
    )
    repo.session.commit()
    RiskControlRequirementService(repo).link_requirement(
        control.uuid_hex,
        requirement.uuid_hex,
        "risk-owner",
    )

    traceability = RiskService(repo).get_traceability(risk.uuid_hex)

    assert any(
        edge["relation_type"] == "implements_requirement"
        and edge["source_uuid"] == control.uuid_hex
        and edge["source_version"] == 1
        and edge["target_uuid"] == requirement.uuid_hex
        and edge["target_version"] == 1
        for edge in traceability
    )

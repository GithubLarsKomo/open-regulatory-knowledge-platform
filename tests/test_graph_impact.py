"""Regression tests for exact-version conservative change impact analysis."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import InvalidObjectIdentifierError, ObjectVersionNotFoundError
from orkp.domain.graph_service import GraphProjectionService


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def test_risk_change_returns_connected_exact_versions_with_paths(repo):
    product, _ = repo.create_object(
        "product",
        {"product_id": "P-IMPACT", "name": "Impact Product"},
        "owner",
        "owner",
    )
    risk, _ = repo.create_object(
        "risk_analysis",
        {"risk_id": "RISK-IMPACT"},
        "risk-owner",
        "risk-owner",
    )
    control, _ = repo.create_object(
        "risk_control",
        {"control_id": "CTRL-IMPACT"},
        "risk-owner",
        "risk-owner",
    )
    repo.create_relation(
        product.object_uuid,
        1,
        risk.object_uuid,
        1,
        "has_risk",
        "risk-owner",
    )
    repo.create_relation(
        risk.object_uuid,
        1,
        control.object_uuid,
        1,
        "controlled_by",
        "risk-owner",
    )
    repo.session.commit()

    result = GraphProjectionService(repo).impact_analysis(risk.uuid_hex, 1, depth=1)

    assert result.changed.object_uuid == risk.uuid_hex
    assert result.changed.object_version == 1
    assert result.approval_authority == "object_store"
    assert result.read_only is True
    assert result.propagation_policy == "bidirectional_active_relations"
    assert {(item.node.object_uuid, item.distance) for item in result.impacted} == {
        (product.uuid_hex, 1),
        (control.uuid_hex, 1),
    }
    assert all(item.path[0].object_uuid == risk.uuid_hex for item in result.impacted)
    assert all(len(item.relation_path) == 1 for item in result.impacted)


def test_impact_returns_deterministic_shortest_paths(repo):
    product, _ = repo.create_object(
        "product", {"product_id": "P-PATH"}, "owner", "owner"
    )
    claim, _ = repo.create_object(
        "claim",
        {
            "claim_type": "clinical",
            "claim_category": "clinical",
            "confidence": "high",
            "severity": "medium",
            "jurisdiction": "EU",
            "language": "en",
            "wording": "Path claim",
            "regulatory_scope": [],
        },
        "claim-owner",
        "claim-owner",
    )
    evidence, _ = repo.create_object(
        "evidence",
        {"evidence_type": "literature", "title": "Path evidence"},
        "evidence-owner",
        "evidence-owner",
    )
    repo.create_relation(
        product.object_uuid, 1, claim.object_uuid, 1, "has_claim", "owner"
    )
    repo.create_relation(
        evidence.object_uuid, 1, claim.object_uuid, 1, "supported_by", "owner"
    )
    repo.session.commit()

    service = GraphProjectionService(repo)
    first = service.impact_analysis(product.uuid_hex, 1, depth=2)
    second = service.impact_analysis(product.uuid_hex, 1, depth=2)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    evidence_impact = next(
        item for item in first.impacted if item.node.object_uuid == evidence.uuid_hex
    )
    assert evidence_impact.distance == 2
    assert [(ref.object_uuid, ref.object_version) for ref in evidence_impact.path] == [
        (product.uuid_hex, 1),
        (claim.uuid_hex, 1),
        (evidence.uuid_hex, 1),
    ]
    assert len(evidence_impact.relation_path) == 2


def test_impact_distinguishes_versions_and_historical_roots(repo):
    product, _ = repo.create_object(
        "product", {"product_id": "P-VERSION"}, "owner", "owner"
    )
    claim, _ = repo.create_object(
        "claim",
        {
            "claim_type": "clinical",
            "claim_category": "clinical",
            "confidence": "high",
            "severity": "medium",
            "jurisdiction": "EU",
            "language": "en",
            "wording": "Impact v1",
            "regulatory_scope": [],
        },
        "claim-owner",
        "claim-owner",
    )
    evidence, _ = repo.create_object(
        "evidence",
        {"evidence_type": "literature", "title": "Version evidence"},
        "evidence-owner",
        "evidence-owner",
    )
    repo.create_relation(
        product.object_uuid, 1, claim.object_uuid, 1, "has_claim", "owner"
    )
    repo.create_version(
        claim.object_uuid,
        {
            "claim_type": "clinical",
            "claim_category": "clinical",
            "confidence": "high",
            "severity": "medium",
            "jurisdiction": "EU",
            "language": "en",
            "wording": "Impact v2",
            "regulatory_scope": [],
        },
        "claim-owner",
    )
    repo.create_relation(
        evidence.object_uuid, 1, claim.object_uuid, 2, "supported_by", "owner"
    )
    repo.session.commit()

    service = GraphProjectionService(repo)
    v1 = service.impact_analysis(claim.uuid_hex, 1, depth=1)
    v2 = service.impact_analysis(claim.uuid_hex, 2, depth=1)

    assert {(item.node.object_uuid, item.node.object_version) for item in v1.impacted} == {
        (product.uuid_hex, 1)
    }
    assert {(item.node.object_uuid, item.node.object_version) for item in v2.impacted} == {
        (evidence.uuid_hex, 1)
    }


def test_inactive_relation_is_excluded_from_impact(repo):
    product, _ = repo.create_object(
        "product", {"product_id": "P-INACTIVE"}, "owner", "owner"
    )
    claim, _ = repo.create_object(
        "claim",
        {
            "claim_type": "clinical",
            "claim_category": "clinical",
            "confidence": "high",
            "severity": "medium",
            "jurisdiction": "EU",
            "language": "en",
            "wording": "Inactive claim",
            "regulatory_scope": [],
        },
        "claim-owner",
        "claim-owner",
    )
    relation = repo.create_relation(
        product.object_uuid, 1, claim.object_uuid, 1, "has_claim", "owner"
    )
    repo.session.flush()
    repo.deactivate_relation(relation.relation_uuid, "owner", "retired")
    repo.session.commit()

    result = GraphProjectionService(repo).impact_analysis(product.uuid_hex, 1, depth=1)

    assert result.impacted == []
    assert result.edges == []


def test_impact_is_read_only_and_validates_root(repo):
    product, _ = repo.create_object(
        "product", {"product_id": "P-READONLY"}, "owner", "owner"
    )
    repo.session.commit()
    service = GraphProjectionService(repo)
    events_before = len(repo.get_event_history(product.object_uuid))

    result = service.impact_analysis(product.uuid_hex, 1, depth=1)

    assert result.impacted == []
    assert len(repo.get_event_history(product.object_uuid)) == events_before
    with pytest.raises(InvalidObjectIdentifierError):
        service.impact_analysis("not-a-uuid", 1, depth=1)
    with pytest.raises(ObjectVersionNotFoundError):
        service.impact_analysis(product.uuid_hex, 99, depth=1)
    with pytest.raises(InvalidObjectIdentifierError):
        service.impact_analysis(product.uuid_hex, 1, depth=0)

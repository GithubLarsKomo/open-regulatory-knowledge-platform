"""Regression tests for version-aware read-only graph projection."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    InvalidObjectIdentifierError,
    ObjectVersionNotFoundError,
)
from orkp.domain.graph_service import GraphProjectionService


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _objects(repo):
    product, _ = repo.create_object(
        "product",
        {"product_id": "P-GRAPH", "name": "Graph Product"},
        "product-owner",
        "product-owner",
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
            "wording": "Claim version one",
            "regulatory_scope": [],
        },
        "claim-owner",
        "claim-owner",
    )
    evidence, _ = repo.create_object(
        "evidence",
        {
            "evidence_type": "literature",
            "title": "Graph Evidence",
            "quality_rating": "high",
        },
        "evidence-owner",
        "evidence-owner",
    )
    repo.session.commit()
    return product, claim, evidence


def test_traceability_projects_exact_incoming_and_outgoing_relations(repo):
    product, claim, evidence = _objects(repo)
    repo.create_relation(
        product.object_uuid,
        1,
        claim.object_uuid,
        1,
        "has_claim",
        "author",
    )
    repo.create_relation(
        evidence.object_uuid,
        1,
        claim.object_uuid,
        1,
        "supported_by",
        "author",
    )
    repo.session.commit()

    graph = GraphProjectionService(repo).traceability(claim.uuid_hex, 1, depth=1)

    assert graph.root.object_uuid == claim.uuid_hex
    assert graph.root.object_version == 1
    assert graph.approval_authority == "object_store"
    assert graph.read_only is True
    assert {(node.object_uuid, node.object_version) for node in graph.nodes} == {
        (product.uuid_hex, 1),
        (claim.uuid_hex, 1),
        (evidence.uuid_hex, 1),
    }
    assert {edge.relation_type for edge in graph.edges} == {"has_claim", "supported_by"}
    assert all(edge.source.object_version == 1 for edge in graph.edges)
    assert all(edge.target.object_version == 1 for edge in graph.edges)


def test_graph_distinguishes_versions_of_same_object_identity(repo):
    product, claim, evidence = _objects(repo)
    repo.create_relation(
        product.object_uuid,
        1,
        claim.object_uuid,
        1,
        "has_claim",
        "author",
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
            "wording": "Claim version two",
            "regulatory_scope": [],
        },
        "claim-owner",
    )
    repo.create_relation(
        evidence.object_uuid,
        1,
        claim.object_uuid,
        2,
        "supported_by",
        "author",
    )
    repo.session.commit()

    service = GraphProjectionService(repo)
    v1 = service.traceability(claim.uuid_hex, 1)
    v2 = service.traceability(claim.uuid_hex, 2)

    assert {(edge.relation_type, edge.target.object_version) for edge in v1.edges} == {
        ("has_claim", 1)
    }
    assert {(edge.relation_type, edge.target.object_version) for edge in v2.edges} == {
        ("supported_by", 2)
    }
    v1_root = next(node for node in v1.nodes if node.object_uuid == claim.uuid_hex)
    v2_root = next(node for node in v2.nodes if node.object_uuid == claim.uuid_hex)
    assert v1_root.label == "Claim version one"
    assert v1_root.is_current_version is False
    assert v2_root.label == "Claim version two"
    assert v2_root.is_current_version is True


def test_inactive_relations_are_not_projected(repo):
    product, claim, _ = _objects(repo)
    relation = repo.create_relation(
        product.object_uuid,
        1,
        claim.object_uuid,
        1,
        "has_claim",
        "author",
    )
    repo.session.flush()
    repo.deactivate_relation(relation.relation_uuid, "author", "superseded")
    repo.session.commit()

    graph = GraphProjectionService(repo).traceability(claim.uuid_hex, 1)

    assert [(node.object_uuid, node.object_version) for node in graph.nodes] == [
        (claim.uuid_hex, 1)
    ]
    assert graph.edges == []


def test_depth_two_traverses_across_intermediate_versioned_node(repo):
    product, claim, evidence = _objects(repo)
    repo.create_relation(
        product.object_uuid,
        1,
        claim.object_uuid,
        1,
        "has_claim",
        "author",
    )
    repo.create_relation(
        evidence.object_uuid,
        1,
        claim.object_uuid,
        1,
        "supported_by",
        "author",
    )
    repo.session.commit()

    depth_one = GraphProjectionService(repo).traceability(product.uuid_hex, 1, depth=1)
    depth_two = GraphProjectionService(repo).traceability(product.uuid_hex, 1, depth=2)

    assert {(node.object_uuid, node.object_version) for node in depth_one.nodes} == {
        (product.uuid_hex, 1),
        (claim.uuid_hex, 1),
    }
    assert {(node.object_uuid, node.object_version) for node in depth_two.nodes} == {
        (product.uuid_hex, 1),
        (claim.uuid_hex, 1),
        (evidence.uuid_hex, 1),
    }


def test_projection_order_is_deterministic_and_duplicate_free(repo):
    product, claim, evidence = _objects(repo)
    repo.create_relation(
        product.object_uuid,
        1,
        claim.object_uuid,
        1,
        "has_claim",
        "author",
    )
    repo.create_relation(
        evidence.object_uuid,
        1,
        claim.object_uuid,
        1,
        "supported_by",
        "author",
    )
    repo.session.commit()

    service = GraphProjectionService(repo)
    first = service.traceability(claim.uuid_hex, 1, depth=2)
    second = service.traceability(claim.uuid_hex, 1, depth=2)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert len(first.nodes) == len(
        {(n.object_uuid, n.object_version) for n in first.nodes}
    )
    assert len(first.edges) == len({edge.relation_uuid for edge in first.edges})


def test_projection_is_read_only_and_preserves_object_store_authority(repo):
    _, claim, _ = _objects(repo)
    events_before = len(repo.get_event_history(claim.object_uuid))
    state_before = claim.lifecycle_state
    version_before = claim.current_version

    graph = GraphProjectionService(repo).traceability(claim.uuid_hex, 1, depth=0)

    assert graph.approval_authority == "object_store"
    assert graph.read_only is True
    assert claim.lifecycle_state == state_before
    assert claim.current_version == version_before
    assert len(repo.get_event_history(claim.object_uuid)) == events_before


def test_invalid_uuid_and_missing_version_are_typed_errors(repo):
    _, claim, _ = _objects(repo)
    service = GraphProjectionService(repo)

    with pytest.raises(InvalidObjectIdentifierError):
        service.traceability("not-a-uuid", 1)
    with pytest.raises(ObjectVersionNotFoundError):
        service.traceability(claim.uuid_hex, 99)

"""REST regressions for read-only version-aware traceability graph queries."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from orkp.api.main import create_app
from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository


@pytest.fixture
def api_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    client = TestClient(create_app(session_factory_override=session_factory))
    return client, session_factory


def _graph_context(session_factory):
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        product, _ = repo.create_object(
            "product",
            {"product_id": "P-GRAPH-API", "name": "Graph API Product"},
            "owner",
            "owner",
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
                "wording": "Graph API claim v1",
                "regulatory_scope": [],
            },
            "claim-owner",
            "claim-owner",
        )
        repo.create_relation(
            product.object_uuid,
            1,
            claim.object_uuid,
            1,
            "has_claim",
            "owner",
        )
        session.commit()
        return product.uuid_hex, claim.uuid_hex


def test_traceability_graph_api_returns_exact_versioned_read_model(api_context):
    client, session_factory = api_context
    product_uuid, claim_uuid = _graph_context(session_factory)

    response = client.get(
        f"/api/v1/graph/objects/{claim_uuid}/versions/1/traceability",
        params={"depth": 1},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == "traceability-graph-1.0"
    assert body["root"] == {"object_uuid": claim_uuid, "object_version": 1}
    assert body["approval_authority"] == "object_store"
    assert body["read_only"] is True
    assert {
        (node["object_uuid"], node["object_version"]) for node in body["nodes"]
    } == {
        (product_uuid, 1),
        (claim_uuid, 1),
    }
    assert len(body["edges"]) == 1
    assert body["edges"][0]["relation_type"] == "has_claim"


def test_traceability_graph_api_preserves_historical_version_identity(api_context):
    client, session_factory = api_context
    _, claim_uuid = _graph_context(session_factory)
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        claim = repo.get_by_uuid_hex(claim_uuid)
        repo.create_version(
            claim.object_uuid,
            {
                "claim_type": "clinical",
                "claim_category": "clinical",
                "confidence": "high",
                "severity": "medium",
                "jurisdiction": "EU",
                "language": "en",
                "wording": "Graph API claim v2",
                "regulatory_scope": [],
            },
            "claim-owner",
        )
        session.commit()

    v1 = client.get(f"/api/v1/graph/objects/{claim_uuid}/versions/1/traceability")
    v2 = client.get(
        f"/api/v1/graph/objects/{claim_uuid}/versions/2/traceability",
        params={"depth": 0},
    )

    assert v1.status_code == 200
    assert v2.status_code == 200
    v1_root = next(
        node for node in v1.json()["nodes"] if node["object_uuid"] == claim_uuid
    )
    v2_root = next(
        node for node in v2.json()["nodes"] if node["object_uuid"] == claim_uuid
    )
    assert v1_root["object_version"] == 1
    assert v1_root["is_current_version"] is False
    assert v2_root["object_version"] == 2
    assert v2_root["is_current_version"] is True


def test_traceability_graph_api_maps_invalid_uuid_and_missing_version(api_context):
    client, session_factory = api_context
    _, claim_uuid = _graph_context(session_factory)

    invalid = client.get("/api/v1/graph/objects/not-a-uuid/versions/1/traceability")
    missing = client.get(f"/api/v1/graph/objects/{claim_uuid}/versions/99/traceability")

    assert invalid.status_code == 422
    assert missing.status_code == 404

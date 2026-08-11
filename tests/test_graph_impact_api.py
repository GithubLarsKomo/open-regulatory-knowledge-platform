"""REST regressions for exact-version graph impact analysis."""

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


def _impact_context(session_factory):
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        product, _ = repo.create_object(
            "product", {"product_id": "P-IMPACT-API"}, "owner", "owner"
        )
        risk, _ = repo.create_object(
            "risk_analysis", {"risk_id": "RISK-IMPACT-API"}, "risk-owner", "risk-owner"
        )
        control, _ = repo.create_object(
            "risk_control", {"control_id": "CTRL-IMPACT-API"}, "risk-owner", "risk-owner"
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
        session.commit()
        return product.uuid_hex, risk.uuid_hex, control.uuid_hex


def test_impact_api_returns_exact_version_paths(api_context):
    client, session_factory = api_context
    product_uuid, risk_uuid, control_uuid = _impact_context(session_factory)

    response = client.get(
        f"/api/v1/graph/objects/{risk_uuid}/versions/1/impact",
        params={"depth": 1},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == "impact-analysis-1.0"
    assert body["changed"] == {"object_uuid": risk_uuid, "object_version": 1}
    assert body["approval_authority"] == "object_store"
    assert body["read_only"] is True
    assert body["propagation_policy"] == "bidirectional_active_relations"
    assert {(item["node"]["object_uuid"], item["distance"]) for item in body["impacted"]} == {
        (product_uuid, 1),
        (control_uuid, 1),
    }
    assert all(len(item["relation_path"]) == 1 for item in body["impacted"])


def test_impact_api_preserves_historical_version_root(api_context):
    client, session_factory = api_context
    product_uuid, risk_uuid, _ = _impact_context(session_factory)
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        risk = repo.get_by_uuid_hex(risk_uuid)
        repo.create_version(
            risk.object_uuid,
            {"risk_id": "RISK-IMPACT-API-v2"},
            "risk-owner",
        )
        session.commit()

    v1 = client.get(
        f"/api/v1/graph/objects/{risk_uuid}/versions/1/impact",
        params={"depth": 1},
    )
    v2 = client.get(
        f"/api/v1/graph/objects/{risk_uuid}/versions/2/impact",
        params={"depth": 1},
    )

    assert v1.status_code == 200
    assert v2.status_code == 200
    assert product_uuid in {item["node"]["object_uuid"] for item in v1.json()["impacted"]}
    assert v2.json()["impacted"] == []


def test_impact_api_validates_uuid_version_and_depth(api_context):
    client, session_factory = api_context
    _, risk_uuid, _ = _impact_context(session_factory)

    invalid_uuid = client.get("/api/v1/graph/objects/not-a-uuid/versions/1/impact")
    missing_version = client.get(
        f"/api/v1/graph/objects/{risk_uuid}/versions/99/impact"
    )
    invalid_depth = client.get(
        f"/api/v1/graph/objects/{risk_uuid}/versions/1/impact",
        params={"depth": 0},
    )

    assert invalid_uuid.status_code == 422
    assert missing_version.status_code == 404
    assert invalid_depth.status_code == 422

"""API regressions for Product-scoped Performance Claim evidence gaps."""

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
    return TestClient(create_app(session_factory_override=session_factory)), session_factory


def _prepared_product(session_factory):
    with session_factory() as session:
        repo = RegulatoryObjectRepository(session)
        product, _ = repo.create_object("product", {"id": "P-GAP-API"}, "owner", "owner")
        claim, _ = repo.create_object(
            "claim",
            {
                "claim_type": "clinical",
                "claim_category": "clinical",
                "confidence": "high",
                "severity": "medium",
                "jurisdiction": "EU",
                "language": "en",
                "wording": "Clinical performance API claim",
                "regulatory_scope": [],
            },
            "owner",
            "owner",
        )
        repo.create_relation(
            source_uuid=product.object_uuid,
            source_version=1,
            target_uuid=claim.object_uuid,
            target_version=1,
            relation_type="has_claim",
            created_by="owner",
        )
        repo.session.commit()
        return product.uuid_hex


def test_api_returns_product_performance_evidence_gaps(api_context):
    client, session_factory = api_context
    product_uuid = _prepared_product(session_factory)

    response = client.get(
        f"/api/v1/products/{product_uuid}/performance-evidence-gaps"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product"]["object_uuid"] == product_uuid
    assert body["performance_claim_count"] == 1
    assert body["gap_claim_count"] == 1
    assert body["complete"] is False
    assert body["claims"][0]["findings"][0]["rule_code"] == "PERF-EVID-MISSING-001"


def test_api_returns_404_for_missing_product(api_context):
    client, _ = api_context

    response = client.get(
        "/api/v1/products/00000000000000000000000000000001/performance-evidence-gaps"
    )

    assert response.status_code == 404

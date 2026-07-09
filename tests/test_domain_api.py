"""Tests for domain-specific API endpoints — Product, Claim, Evidence."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from orkp.db.models import Base
from orkp.api.main import create_app


@pytest.fixture
def client():
    """Create a test client with in-memory SQLite."""
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    app = create_app(session_factory_override=TestSession)
    return TestClient(app)


class TestProductAPI:
    """Tests for /api/v1/products endpoints."""

    def test_create_product(self, client):
        response = client.post(
            "/api/v1/products",
            params={"owner_user_id": "user-001"},
            json={
                "product_id": "PROD-001",
                "name": "Test IVD Kit",
                "description": "A test product",
                "basic_udi_di": "04250710612345",
                "manufacturer_name": "Test Corp",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["object_type"] == "product"
        assert data["lifecycle_state"] == "draft"
        assert "object_uuid" in data

    def test_list_products(self, client):
        client.post("/api/v1/products", params={"owner_user_id": "u1"}, json={"product_id": "P1", "name": "Product 1"})
        client.post("/api/v1/products", params={"owner_user_id": "u2"}, json={"product_id": "P2", "name": "Product 2"})

        response = client.get("/api/v1/products")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_get_product(self, client):
        create_resp = client.post(
            "/api/v1/products", params={"owner_user_id": "u1"},
            json={"product_id": "P1", "name": "Product 1"},
        )
        uuid = create_resp.json()["object_uuid"]

        response = client.get(f"/api/v1/products/{uuid}")
        assert response.status_code == 200
        assert response.json()["payload"]["product_id"] == "P1"

    def test_product_lifecycle(self, client):
        create_resp = client.post(
            "/api/v1/products", params={"owner_user_id": "u1"},
            json={"product_id": "P1", "name": "Product 1"},
        )
        uuid = create_resp.json()["object_uuid"]

        # Submit
        submit_resp = client.post(f"/api/v1/products/{uuid}/submit", params={"actor_user_id": "u1"})
        assert submit_resp.status_code == 200

        # Approve
        approve_resp = client.post(f"/api/v1/products/{uuid}/approve", params={"actor_user_id": "u2", "comments": "OK"})
        assert approve_resp.status_code == 200

        # Verify state
        get_resp = client.get(f"/api/v1/products/{uuid}")
        assert get_resp.json()["lifecycle_state"] == "approved"

    def test_delete_product(self, client):
        create_resp = client.post(
            "/api/v1/products", params={"owner_user_id": "u1"},
            json={"product_id": "P1", "name": "Product 1"},
        )
        uuid = create_resp.json()["object_uuid"]

        delete_resp = client.delete(f"/api/v1/products/{uuid}", params={"actor_user_id": "u1"})
        assert delete_resp.status_code == 204

        get_resp = client.get(f"/api/v1/products/{uuid}")
        assert get_resp.status_code == 404


class TestClaimAPI:
    """Tests for /api/v1/claims endpoints."""

    def test_create_claim(self, client):
        response = client.post(
            "/api/v1/claims",
            params={"owner_user_id": "user-001"},
            json={
                "claim_type": "performance",
                "jurisdiction": "EU",
                "language": "en",
                "wording": "95% sensitivity",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["object_type"] == "claim"

    def test_get_claim(self, client):
        create_resp = client.post(
            "/api/v1/claims", params={"owner_user_id": "u1"},
            json={"claim_type": "safety", "jurisdiction": "EU", "language": "en", "wording": "Safe device"},
        )
        uuid = create_resp.json()["object_uuid"]

        response = client.get(f"/api/v1/claims/{uuid}")
        assert response.status_code == 200
        assert response.json()["payload"]["wording"] == "Safe device"

    def test_link_evidence_to_claim(self, client):
        # Create claim
        claim_resp = client.post(
            "/api/v1/claims", params={"owner_user_id": "u1"},
            json={"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "Clinical claim"},
        )
        claim_uuid = claim_resp.json()["object_uuid"]

        # Create evidence
        ev_resp = client.post(
            "/api/v1/evidence", params={"owner_user_id": "u1"},
            json={"evidence_type": "literature_reference", "title": "Study 2024", "author": "Smith"},
        )
        ev_uuid = ev_resp.json()["object_uuid"]

        # Link
        link_resp = client.post(
            f"/api/v1/claims/{claim_uuid}/link-evidence",
            params={"evidence_uuid": ev_uuid, "link_type": "supports"},
        )
        assert link_resp.status_code == 200

        # Verify evidence coverage
        coverage_resp = client.get(f"/api/v1/claims/{claim_uuid}/evidence-coverage")
        assert coverage_resp.status_code == 200
        assert coverage_resp.json()["has_evidence"] is True
        assert coverage_resp.json()["approvable"] is True

    def test_claim_evidence_coverage_empty(self, client):
        create_resp = client.post(
            "/api/v1/claims", params={"owner_user_id": "u1"},
            json={"claim_type": "safety", "jurisdiction": "EU", "language": "en", "wording": "Safety claim"},
        )
        uuid = create_resp.json()["object_uuid"]

        coverage_resp = client.get(f"/api/v1/claims/{uuid}/evidence-coverage")
        assert coverage_resp.json()["has_evidence"] is False
        assert coverage_resp.json()["approvable"] is False

    def test_claim_lifecycle(self, client):
        create_resp = client.post(
            "/api/v1/claims", params={"owner_user_id": "u1"},
            json={"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "Test"},
        )
        uuid = create_resp.json()["object_uuid"]

        # Submit
        client.post(f"/api/v1/claims/{uuid}/submit", params={"actor_user_id": "u1"})

        # Approve
        approve_resp = client.post(f"/api/v1/claims/{uuid}/approve", params={"actor_user_id": "u2", "comments": "Good"})
        assert approve_resp.status_code == 200

        get_resp = client.get(f"/api/v1/claims/{uuid}")
        assert get_resp.json()["lifecycle_state"] == "approved"


class TestEvidenceAPI:
    """Tests for /api/v1/evidence endpoints."""

    def test_create_evidence(self, client):
        response = client.post(
            "/api/v1/evidence",
            params={"owner_user_id": "user-001"},
            json={
                "evidence_type": "literature_reference",
                "title": "Clinical Study 2024",
                "author": "Smith et al.",
                "source_reference": "PMID:12345678",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["object_type"] == "evidence"

    def test_get_evidence(self, client):
        create_resp = client.post(
            "/api/v1/evidence", params={"owner_user_id": "u1"},
            json={"evidence_type": "standards_reference", "title": "ISO 14971"},
        )
        uuid = create_resp.json()["object_uuid"]

        response = client.get(f"/api/v1/evidence/{uuid}")
        assert response.status_code == 200
        assert response.json()["payload"]["title"] == "ISO 14971"

    def test_evidence_lifecycle(self, client):
        create_resp = client.post(
            "/api/v1/evidence", params={"owner_user_id": "u1"},
            json={"evidence_type": "clinical_data", "title": "Clinical Data"},
        )
        uuid = create_resp.json()["object_uuid"]

        client.post(f"/api/v1/evidence/{uuid}/submit", params={"actor_user_id": "u1"})
        approve_resp = client.post(f"/api/v1/evidence/{uuid}/approve", params={"actor_user_id": "u2"})
        assert approve_resp.status_code == 200

        get_resp = client.get(f"/api/v1/evidence/{uuid}")
        assert get_resp.json()["lifecycle_state"] == "approved"
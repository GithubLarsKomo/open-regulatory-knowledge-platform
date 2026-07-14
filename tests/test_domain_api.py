"""Tests for domain-specific API endpoints — Product, Claim, Evidence."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker, Session

from orkp.api.main import create_app
from orkp.db.models import Base


@pytest.fixture(scope="function")
def client():
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, echo=False,
    )

    @sa_event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    app = create_app(session_factory_override=TestSession)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Product API
# ---------------------------------------------------------------------------

_VALID_PRODUCT = {
    "product_id": "PROD-001",
    "name": "Test IVD Kit",
    "product_kind": "kit",
    "legal_manufacturer": "Test Corp",
    "intended_purpose": "Detection of SARS-CoV-2",
    "regulatory_status": "development",
    "description": "A test product",
    "basic_udi_di": "04250710612345",
    "applicable_regulations": ["EU 2017/746"],
}


class TestProductAPI:
    def test_create_product(self, client):
        resp = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["object_type"] == "product"
        assert data["lifecycle_state"] == "draft"

    def test_list_products(self, client):
        client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        resp = client.get("/api/v1/products")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_get_product(self, client):
        create = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        uuid = create.json()["object_uuid"]
        resp = client.get(f"/api/v1/products/{uuid}")
        assert resp.status_code == 200
        assert resp.json()["payload"]["product_id"] == "PROD-001"

    def test_product_lifecycle(self, client):
        create = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        uuid = create.json()["object_uuid"]

        # Submit
        r = client.post(f"/api/v1/products/{uuid}/submit", params={"actor_user_id": "u1"})
        assert r.status_code == 200

        # Approve (will fail completeness without claims/risks)
        r = client.post(f"/api/v1/products/{uuid}/approve", params={"actor_user_id": "u2"})
        assert r.status_code == 422  # completeness check

    def test_delete_product(self, client):
        create = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        uuid = create.json()["object_uuid"]
        resp = client.delete(f"/api/v1/products/{uuid}", params={"actor_user_id": "u1"})
        assert resp.status_code == 204

    def test_reject_unknown_fields(self, client):
        """Unknown payload fields are rejected with 422."""
        payload = {**_VALID_PRODUCT, "unknown_field": "should_fail"}
        resp = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=payload)
        assert resp.status_code == 422

    def test_reject_invalid_product_kind(self, client):
        payload = {**_VALID_PRODUCT, "product_kind": "invalid_kind"}
        resp = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=payload)
        assert resp.status_code == 422

    def test_reject_duplicate_regulations(self, client):
        payload = {**_VALID_PRODUCT, "applicable_regulations": ["EU 2017/746", "EU 2017/746"]}
        resp = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=payload)
        assert resp.status_code == 422

    def test_add_device_variant(self, client):
        create = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        uuid = create.json()["object_uuid"]

        device_payload = {
            "device_id": "DEV-001",
            "name": "Test Device",
            "device_kind": "reagent",
        }
        resp = client.post(
            f"/api/v1/products/{uuid}/devices",
            params={"actor_user_id": "u1"},
            json=device_payload,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["object_type"] == "device"

    def test_list_device_variants(self, client):
        create = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        uuid = create.json()["object_uuid"]

        dp = {"device_id": "D1", "name": "Dev1", "device_kind": "reagent"}
        client.post(f"/api/v1/products/{uuid}/devices", params={"actor_user_id": "u1"}, json=dp)

        resp = client.get(f"/api/v1/products/{uuid}/devices")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_product_completeness(self, client):
        create = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        uuid = create.json()["object_uuid"]

        resp = client.get(f"/api/v1/products/{uuid}/completeness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["complete"] is False  # no claims or risks
        assert "missing_relationships" in data

    def test_link_claim_and_risk(self, client):
        create = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        puid = create.json()["object_uuid"]

        # Create claim
        cr = client.post("/api/v1/claims", params={"owner_user_id": "u1"},
                         json={"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "Test claim"})
        cuid = cr.json()["object_uuid"]

        # Create risk (as a claim for testing)
        rr = client.post("/api/v1/claims", params={"owner_user_id": "u1"},
                         json={"claim_type": "safety", "jurisdiction": "EU", "language": "en", "wording": "Risk statement"})
        rid = rr.json()["object_uuid"]

        # Link claim
        r1 = client.post(f"/api/v1/products/{puid}/claims/{cuid}", params={"actor_user_id": "u1"})
        assert r1.status_code == 200

        # Link risk
        r2 = client.post(f"/api/v1/products/{puid}/risks/{rid}", params={"actor_user_id": "u1"})
        assert r2.status_code == 200

        # Now completeness should pass
        comp = client.get(f"/api/v1/products/{puid}/completeness")
        assert comp.json()["complete"] is True


# ---------------------------------------------------------------------------
# Claim API
# ---------------------------------------------------------------------------

class TestClaimAPI:
    def test_create_claim(self, client):
        resp = client.post("/api/v1/claims", params={"owner_user_id": "u1"},
                           json={"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "Test"})
        assert resp.status_code == 201
        assert resp.json()["object_type"] == "claim"

    def test_get_claim(self, client):
        cr = client.post("/api/v1/claims", params={"owner_user_id": "u1"},
                         json={"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "Test"})
        uuid = cr.json()["object_uuid"]
        resp = client.get(f"/api/v1/claims/{uuid}")
        assert resp.status_code == 200

    def test_link_evidence_to_claim(self, client):
        cr = client.post("/api/v1/claims", params={"owner_user_id": "u1"},
                         json={"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "Test"})
        cuid = cr.json()["object_uuid"]

        er = client.post("/api/v1/evidence", params={"owner_user_id": "u1"},
                         json={"evidence_type": "literature_reference", "title": "Study 2024"})
        euid = er.json()["object_uuid"]

        resp = client.post(f"/api/v1/claims/{cuid}/link-evidence",
                           params={"evidence_uuid": euid, "link_type": "supports_claim"})
        assert resp.status_code == 200, resp.text

    def test_claim_evidence_coverage_empty(self, client):
        cr = client.post("/api/v1/claims", params={"owner_user_id": "u1"},
                         json={"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "Test"})
        uuid = cr.json()["object_uuid"]
        resp = client.get(f"/api/v1/claims/{uuid}/evidence-coverage")
        assert resp.json()["has_evidence"] is False

    def test_claim_lifecycle(self, client):
        cr = client.post("/api/v1/claims", params={"owner_user_id": "u1"},
                         json={"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "Test"})
        uuid = cr.json()["object_uuid"]

        r = client.post(f"/api/v1/claims/{uuid}/submit", params={"actor_user_id": "u1"})
        assert r.status_code == 200

        r = client.post(f"/api/v1/claims/{uuid}/approve", params={"actor_user_id": "u2"})
        assert r.status_code == 200

    def test_reject_unknown_claim_fields(self, client):
        """evidence_links in claim payload should be rejected."""
        resp = client.post("/api/v1/claims", params={"owner_user_id": "u1"},
                           json={"claim_type": "clinical", "jurisdiction": "EU", "language": "en",
                                 "wording": "Test", "evidence_links": ["fake-uuid"]})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Evidence API
# ---------------------------------------------------------------------------

class TestEvidenceAPI:
    def test_create_evidence(self, client):
        resp = client.post("/api/v1/evidence", params={"owner_user_id": "u1"},
                           json={"evidence_type": "literature_reference", "title": "Study 2024"})
        assert resp.status_code == 201
        assert resp.json()["object_type"] == "evidence"

    def test_get_evidence(self, client):
        er = client.post("/api/v1/evidence", params={"owner_user_id": "u1"},
                         json={"evidence_type": "literature_reference", "title": "Study"})
        uuid = er.json()["object_uuid"]
        resp = client.get(f"/api/v1/evidence/{uuid}")
        assert resp.status_code == 200

    def test_evidence_lifecycle(self, client):
        er = client.post("/api/v1/evidence", params={"owner_user_id": "u1"},
                         json={"evidence_type": "literature_reference", "title": "Study"})
        uuid = er.json()["object_uuid"]

        r = client.post(f"/api/v1/evidence/{uuid}/submit", params={"actor_user_id": "u1"})
        assert r.status_code == 200

        r = client.post(f"/api/v1/evidence/{uuid}/approve", params={"actor_user_id": "u2"})
        assert r.status_code == 200
"""Tests for domain-specific API endpoints — Product, Claim, Evidence."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker

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

_VALID_CLAIM = {
    "claim_type": "clinical",
    "claim_category": "clinical",
    "confidence": "high",
    "severity": "medium",
    "jurisdiction": "EU",
    "language": "en",
    "wording": "Test claim",
}

_VALID_EVIDENCE = {
    "evidence_type": "literature",
    "title": "Study 2024",
    "quality_rating": "medium",
}


# ---------------------------------------------------------------------------
# Product API
# ---------------------------------------------------------------------------

class TestProductAPI:
    def test_create_product(self, client):
        resp = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        assert resp.status_code == 201, resp.text
        assert resp.json()["object_type"] == "product"

    def test_list_products(self, client):
        client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        resp = client.get("/api/v1/products")
        assert resp.status_code == 200 and len(resp.json()) == 1

    def test_get_product(self, client):
        cr = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        uid = cr.json()["object_uuid"]
        resp = client.get(f"/api/v1/products/{uid}")
        assert resp.status_code == 200

    def test_product_lifecycle(self, client):
        cr = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        uid = cr.json()["object_uuid"]
        assert client.post(f"/api/v1/products/{uid}/submit", params={"actor_user_id": "u1"}).status_code == 200
        assert client.post(f"/api/v1/products/{uid}/approve", params={"actor_user_id": "u2"}).status_code == 422

    def test_delete_product(self, client):
        cr = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        uid = cr.json()["object_uuid"]
        assert client.delete(f"/api/v1/products/{uid}", params={"actor_user_id": "u1"}).status_code == 204

    def test_reject_unknown_fields(self, client):
        p = {**_VALID_PRODUCT, "unknown_field": "fail"}
        assert client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=p).status_code == 422

    def test_reject_invalid_product_kind(self, client):
        p = {**_VALID_PRODUCT, "product_kind": "invalid"}
        assert client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=p).status_code == 422

    def test_reject_duplicate_regulations(self, client):
        p = {**_VALID_PRODUCT, "applicable_regulations": ["EU 2017/746", "EU 2017/746"]}
        assert client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=p).status_code == 422

    def test_add_device_variant(self, client):
        cr = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        uid = cr.json()["object_uuid"]
        dp = {"device_id": "D1", "name": "Dev1", "device_kind": "reagent"}
        resp = client.post(f"/api/v1/products/{uid}/devices", params={"actor_user_id": "u1"}, json=dp)
        assert resp.status_code == 201 and resp.json()["object_type"] == "device"

    def test_list_device_variants(self, client):
        cr = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        uid = cr.json()["object_uuid"]
        dp = {"device_id": "D1", "name": "Dev1", "device_kind": "reagent"}
        client.post(f"/api/v1/products/{uid}/devices", params={"actor_user_id": "u1"}, json=dp)
        assert len(client.get(f"/api/v1/products/{uid}/devices").json()) == 1

    def test_product_completeness(self, client):
        cr = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        uid = cr.json()["object_uuid"]
        resp = client.get(f"/api/v1/products/{uid}/completeness")
        assert resp.json()["complete"] is False

    def test_link_claim_and_risk(self, client):
        cr = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT)
        puid = cr.json()["object_uuid"]
        cuid = client.post("/api/v1/claims", params={"owner_user_id": "u1"}, json=_VALID_CLAIM).json()["object_uuid"]
        rid = client.post("/api/v1/claims", params={"owner_user_id": "u1"},
                          json={**_VALID_CLAIM, "claim_type": "safety", "claim_category": "safety", "severity": "high"}).json()["object_uuid"]
        assert client.post(f"/api/v1/products/{puid}/claims/{cuid}", params={"actor_user_id": "u1"}).status_code == 200
        assert client.post(f"/api/v1/products/{puid}/risks/{rid}", params={"actor_user_id": "u1"}).status_code == 200
        assert client.get(f"/api/v1/products/{puid}/completeness").json()["complete"] is True


# ---------------------------------------------------------------------------
# Claim API
# ---------------------------------------------------------------------------

class TestClaimAPI:
    def test_create_claim(self, client):
        resp = client.post("/api/v1/claims", params={"owner_user_id": "u1"}, json=_VALID_CLAIM)
        assert resp.status_code == 201 and resp.json()["object_type"] == "claim"

    def test_get_claim(self, client):
        uid = client.post("/api/v1/claims", params={"owner_user_id": "u1"}, json=_VALID_CLAIM).json()["object_uuid"]
        assert client.get(f"/api/v1/claims/{uid}").status_code == 200

    def test_link_evidence_to_claim(self, client):
        cuid = client.post("/api/v1/claims", params={"owner_user_id": "u1"}, json=_VALID_CLAIM).json()["object_uuid"]
        euid = client.post("/api/v1/evidence", params={"owner_user_id": "u1"}, json=_VALID_EVIDENCE).json()["object_uuid"]
        resp = client.post(f"/api/v1/claims/{cuid}/link-evidence", params={"evidence_uuid": euid, "link_type": "supported_by"})
        assert resp.status_code == 200, resp.text

    def test_claim_evidence_coverage_empty(self, client):
        uid = client.post("/api/v1/claims", params={"owner_user_id": "u1"}, json=_VALID_CLAIM).json()["object_uuid"]
        assert client.get(f"/api/v1/claims/{uid}/evidence-coverage").json()["has_evidence"] is False

    def test_claim_lifecycle(self, client):
        uid = client.post("/api/v1/claims", params={"owner_user_id": "u1"}, json=_VALID_CLAIM).json()["object_uuid"]
        assert client.post(f"/api/v1/claims/{uid}/submit", params={"actor_user_id": "u1"}).status_code == 200
        # Approve should fail without evidence
        assert client.post(f"/api/v1/claims/{uid}/approve", params={"actor_user_id": "u2"}).status_code == 422

    def test_approve_with_evidence(self, client):
        # Create product
        puid = client.post("/api/v1/products", params={"owner_user_id": "u1"}, json=_VALID_PRODUCT).json()["object_uuid"]
        # Create claim
        cuid = client.post("/api/v1/claims", params={"owner_user_id": "u1"}, json=_VALID_CLAIM).json()["object_uuid"]
        # Link product to claim
        client.post(f"/api/v1/products/{puid}/claims/{cuid}", params={"actor_user_id": "u1"})
        # Create and approve evidence
        euid = client.post("/api/v1/evidence", params={"owner_user_id": "u1"}, json=_VALID_EVIDENCE).json()["object_uuid"]
        client.post(f"/api/v1/evidence/{euid}/submit", params={"actor_user_id": "u1"})
        client.post(f"/api/v1/evidence/{euid}/approve", params={"actor_user_id": "u2"})
        # Link evidence to claim
        client.post(f"/api/v1/claims/{cuid}/link-evidence", params={"evidence_uuid": euid, "link_type": "supported_by"})
        client.post(f"/api/v1/claims/{cuid}/submit", params={"actor_user_id": "u1"})
        assert client.post(f"/api/v1/claims/{cuid}/approve", params={"actor_user_id": "u2"}).status_code == 200

    def test_coverage_report(self, client):
        uid = client.post("/api/v1/claims", params={"owner_user_id": "u1"}, json=_VALID_CLAIM).json()["object_uuid"]
        resp = client.get(f"/api/v1/claims/{uid}/coverage")
        assert resp.status_code == 200

    def test_claim_history(self, client):
        uid = client.post("/api/v1/claims", params={"owner_user_id": "u1"}, json=_VALID_CLAIM).json()["object_uuid"]
        resp = client.get(f"/api/v1/claims/{uid}/history")
        assert resp.status_code == 200

    def test_reject_unknown_claim_fields(self, client):
        p = {**_VALID_CLAIM, "evidence_links": ["fake"]}
        assert client.post("/api/v1/claims", params={"owner_user_id": "u1"}, json=p).status_code == 422


# ---------------------------------------------------------------------------
# Evidence API
# ---------------------------------------------------------------------------

class TestEvidenceAPI:
    def test_create_evidence(self, client):
        resp = client.post("/api/v1/evidence", params={"owner_user_id": "u1"}, json=_VALID_EVIDENCE)
        assert resp.status_code == 201 and resp.json()["object_type"] == "evidence"

    def test_get_evidence(self, client):
        uid = client.post("/api/v1/evidence", params={"owner_user_id": "u1"}, json=_VALID_EVIDENCE).json()["object_uuid"]
        assert client.get(f"/api/v1/evidence/{uid}").status_code == 200

    def test_evidence_lifecycle(self, client):
        uid = client.post("/api/v1/evidence", params={"owner_user_id": "u1"}, json=_VALID_EVIDENCE).json()["object_uuid"]
        assert client.post(f"/api/v1/evidence/{uid}/submit", params={"actor_user_id": "u1"}).status_code == 200
        assert client.post(f"/api/v1/evidence/{uid}/approve", params={"actor_user_id": "u2"}).status_code == 200

    def test_evidence_claims(self, client):
        uid = client.post("/api/v1/evidence", params={"owner_user_id": "u1"}, json=_VALID_EVIDENCE).json()["object_uuid"]
        resp = client.get(f"/api/v1/evidence/{uid}/claims")
        assert resp.status_code == 200

    def test_evidence_coverage(self, client):
        uid = client.post("/api/v1/evidence", params={"owner_user_id": "u1"}, json=_VALID_EVIDENCE).json()["object_uuid"]
        resp = client.get(f"/api/v1/evidence/{uid}/coverage")
        assert resp.status_code == 200

    def test_evidence_quality(self, client):
        uid = client.post("/api/v1/evidence", params={"owner_user_id": "u1"}, json=_VALID_EVIDENCE).json()["object_uuid"]
        resp = client.get(f"/api/v1/evidence/{uid}/quality")
        assert resp.status_code == 200
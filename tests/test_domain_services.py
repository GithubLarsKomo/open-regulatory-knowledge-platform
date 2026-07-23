"""Tests for domain services — Product, Claim, Evidence."""

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.services import ProductService, ClaimService, EvidenceService
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    ProductCompletenessError,
    ClaimApprovalError,
)


@pytest.fixture
def repo_session():
    engine = create_engine("sqlite://", echo=False)

    @sa_event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    repo = RegulatoryObjectRepository(session)
    yield session, repo
    session.close()
    transaction.rollback()
    connection.close()


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


class TestProductService:
    def test_create(self, repo_session):
        session, repo = repo_session
        s = ProductService(repo)
        obj, _ = s.create(_VALID_PRODUCT, "u1")
        assert obj.object_type == "product"

    def test_list(self, repo_session):
        session, repo = repo_session
        s = ProductService(repo)
        s.create(_VALID_PRODUCT, "u1")
        s.create({**_VALID_PRODUCT, "product_id": "P2"}, "u2")
        assert len(s.list()) == 2

    def test_approve_fails_without_completeness(self, repo_session):
        session, repo = repo_session
        s = ProductService(repo)
        obj, _ = s.create(_VALID_PRODUCT, "u1")
        s.submit_for_review(obj.uuid_hex, "u1")
        with pytest.raises(ProductCompletenessError):
            s.approve(obj.uuid_hex, "u2")

    def test_soft_delete(self, repo_session):
        session, repo = repo_session
        s = ProductService(repo)
        obj, _ = s.create(_VALID_PRODUCT, "u1")
        s.soft_delete(obj.uuid_hex, "u1")
        assert s.get(obj.uuid_hex) is None

    def test_add_device_variant(self, repo_session):
        session, repo = repo_session
        s = ProductService(repo)
        obj, _ = s.create(_VALID_PRODUCT, "u1")
        device = s.add_device_variant(
            obj.uuid_hex,
            {"device_id": "D1", "name": "Dev1", "device_kind": "reagent"},
            "u1",
        )
        assert device.object_type == "device"
        assert len(s.list_devices(obj.uuid_hex)) == 1

    def test_link_claim_and_risk(self, repo_session):
        session, repo = repo_session
        ps = ProductService(repo)
        cs = ClaimService(repo)
        obj, _ = ps.create(_VALID_PRODUCT, "u1")
        c, _ = cs.create(_VALID_CLAIM, "u1")
        # Create a risk_analysis object
        r, _ = repo.create_object(
            object_type="risk_analysis",
            payload={
                "risk_id": "R1",
                "title": "Test Risk",
                "severity": "moderate",
                "probability": "possible",
            },
            owner_user_id="u1",
            created_by="u1",
        )
        session.commit()
        risk_obj = r  # create_object returns (obj, version)
        ps.link_claim(obj.uuid_hex, c.uuid_hex, "u1")
        ps.link_risk(obj.uuid_hex, risk_obj.uuid_hex, "u1")
        assert len(ps.list_claims(obj.uuid_hex)) == 1
        assert len(ps.list_risks(obj.uuid_hex)) == 1


class TestClaimService:
    def test_create(self, repo_session):
        session, repo = repo_session
        s = ClaimService(repo)
        obj, _ = s.create(_VALID_CLAIM, "u1")
        assert obj.object_type == "claim"

    def test_link_evidence(self, repo_session):
        session, repo = repo_session
        cs = ClaimService(repo)
        es = EvidenceService(repo)
        c, _ = cs.create(_VALID_CLAIM, "u1")
        e, _ = es.create(_VALID_EVIDENCE, "u1")
        cs.link_evidence(c.uuid_hex, e.uuid_hex, "supported_by")
        assert len(cs.list_evidence(c.uuid_hex)) == 1

    def test_approve_fails_without_evidence(self, repo_session):
        session, repo = repo_session
        s = ClaimService(repo)
        obj, _ = s.create(_VALID_CLAIM, "u1")
        s.submit_for_review(obj.uuid_hex, "u1")
        with pytest.raises(ClaimApprovalError):
            s.approve(obj.uuid_hex, "u2")

    def test_approve_with_evidence(self, repo_session):
        session, repo = repo_session
        cs = ClaimService(repo)
        es = EvidenceService(repo)
        ps = ProductService(repo)
        c, _ = cs.create(_VALID_CLAIM, "u1")
        e, _ = es.create(_VALID_EVIDENCE, "u1")
        # Create a product and link it
        p, _ = ps.create(_VALID_PRODUCT, "u1")
        ps.link_claim(p.uuid_hex, c.uuid_hex, "u1")
        # Approve evidence first
        es.submit_for_review(e.uuid_hex, "u1")
        es.approve(e.uuid_hex, "u2")
        # Link evidence to claim
        cs.link_evidence(c.uuid_hex, e.uuid_hex, "supported_by")
        cs.submit_for_review(c.uuid_hex, "u1")
        cs.approve(c.uuid_hex, "u2", "Approved")
        data = cs.get_with_payload(c.uuid_hex)
        assert data["lifecycle_state"] == "approved"

    def test_coverage_report(self, repo_session):
        session, repo = repo_session
        s = ClaimService(repo)
        obj, _ = s.create(_VALID_CLAIM, "u1")
        report = s.get_coverage_report(obj.uuid_hex)
        assert report["total_evidence_relations"] == 0

    def test_history(self, repo_session):
        session, repo = repo_session
        s = ClaimService(repo)
        obj, _ = s.create(_VALID_CLAIM, "u1")
        h = s.get_history(obj.uuid_hex)
        assert h["version_count"] >= 1

    def test_typed_exceptions(self, repo_session):
        session, repo = repo_session
        s = ClaimService(repo)
        with pytest.raises(ObjectNotFoundError):
            s.link_evidence(
                "00000000000000000000000000000000", "00000000000000000000000000000000"
            )


class TestEvidenceService:
    def test_create(self, repo_session):
        session, repo = repo_session
        s = EvidenceService(repo)
        obj, _ = s.create(_VALID_EVIDENCE, "u1")
        assert obj.object_type == "evidence"

    def test_list(self, repo_session):
        session, repo = repo_session
        s = EvidenceService(repo)
        s.create(_VALID_EVIDENCE, "u1")
        s.create({**_VALID_EVIDENCE, "title": "S2"}, "u2")
        assert len(s.list()) == 2

    def test_lifecycle(self, repo_session):
        session, repo = repo_session
        s = EvidenceService(repo)
        obj, _ = s.create(_VALID_EVIDENCE, "u1")
        s.submit_for_review(obj.uuid_hex, "u1")
        s.approve(obj.uuid_hex, "u2")
        data = s.get_with_payload(obj.uuid_hex)
        assert data["lifecycle_state"] == "approved"

    def test_find_claims(self, repo_session):
        session, repo = repo_session
        cs = ClaimService(repo)
        es = EvidenceService(repo)
        c, _ = cs.create(_VALID_CLAIM, "u1")
        e, _ = es.create(_VALID_EVIDENCE, "u1")
        cs.link_evidence(c.uuid_hex, e.uuid_hex, "supported_by")
        claims = es.find_claims(e.uuid_hex)
        assert len(claims) == 1

    def test_coverage(self, repo_session):
        session, repo = repo_session
        s = EvidenceService(repo)
        obj, _ = s.create(_VALID_EVIDENCE, "u1")
        cov = s.get_coverage(obj.uuid_hex)
        assert cov["total_active_claim_relations"] == 0

    def test_quality_summary(self, repo_session):
        session, repo = repo_session
        s = EvidenceService(repo)
        obj, _ = s.create(_VALID_EVIDENCE, "u1")
        q = s.get_quality_summary(obj.uuid_hex)
        assert q["quality_rating"] == "medium"

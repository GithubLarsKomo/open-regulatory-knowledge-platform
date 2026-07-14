"""Tests for domain services — Product, Claim, Evidence."""

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker, Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.services import ProductService, ClaimService, EvidenceService, DeviceService
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    InvalidLifecycleTransitionError,
    ProductCompletenessError,
    OptimisticLockError,
    ImmutableVersionError,
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


_VALID_PRODUCT_PAYLOAD = {
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


class TestProductService:
    def test_create_product(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        obj, version = service.create(_VALID_PRODUCT_PAYLOAD, "u1")
        assert obj.object_type == 'product'
        assert obj.lifecycle_state == 'draft'

    def test_list_products(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        service.create(_VALID_PRODUCT_PAYLOAD, "u1")
        service.create({**_VALID_PRODUCT_PAYLOAD, "product_id": "P2"}, "u2")
        assert len(service.list()) == 2

    def test_submit_and_approve_with_relations(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        claim_service = ClaimService(repo)

        # Create product
        obj, _ = service.create(_VALID_PRODUCT_PAYLOAD, "u1")

        # Create claim and link
        c, _ = claim_service.create(
            {"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "Test claim"}, "u1"
        )
        # Create another claim as "risk" stand-in
        r, _ = claim_service.create(
            {"claim_type": "safety", "jurisdiction": "EU", "language": "en", "wording": "Risk"}, "u1"
        )
        service.link_claim(obj.uuid_hex, c.uuid_hex, "u1")
        service.link_risk(obj.uuid_hex, r.uuid_hex, "u1")

        # Submit and approve should work now
        service.submit_for_review(obj.uuid_hex, "u1")
        service.approve(obj.uuid_hex, "u2", "Approved")
        data = service.get_with_payload(obj.uuid_hex)
        assert data['lifecycle_state'] == 'approved'

    def test_approve_fails_without_completeness(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        obj, _ = service.create(_VALID_PRODUCT_PAYLOAD, "u1")
        service.submit_for_review(obj.uuid_hex, "u1")
        with pytest.raises(ProductCompletenessError):
            service.approve(obj.uuid_hex, "u2")

    def test_soft_delete(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        obj, _ = service.create(_VALID_PRODUCT_PAYLOAD, "u1")
        service.soft_delete(obj.uuid_hex, "u1")
        assert service.get(obj.uuid_hex) is None

    def test_add_device_variant(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        obj, _ = service.create(_VALID_PRODUCT_PAYLOAD, "u1")

        device = service.add_device_variant(
            obj.uuid_hex,
            {"device_id": "D1", "name": "Dev1", "device_kind": "reagent"},
            "u1",
        )
        assert device.object_type == 'device'
        devices = service.list_devices(obj.uuid_hex)
        assert len(devices) == 1
        assert devices[0].object_uuid == device.object_uuid

    def test_add_device_variant_nonexistent_product(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        with pytest.raises(ObjectNotFoundError):
            service.add_device_variant("00000000000000000000000000000000",
                                       {"device_id": "D1", "name": "Dev1", "device_kind": "reagent"}, "u1")

    def test_completeness_evaluation(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        obj, _ = service.create(_VALID_PRODUCT_PAYLOAD, "u1")
        result = service.get_completeness(obj.uuid_hex)
        assert result['complete'] is False
        assert 'missing_relationships' in result

    def test_link_claim_and_risk(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        claim_service = ClaimService(repo)

        obj, _ = service.create(_VALID_PRODUCT_PAYLOAD, "u1")
        c, _ = claim_service.create(
            {"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "C1"}, "u1"
        )
        r, _ = claim_service.create(
            {"claim_type": "safety", "jurisdiction": "EU", "language": "en", "wording": "R1"}, "u1"
        )

        service.link_claim(obj.uuid_hex, c.uuid_hex, "u1")
        service.link_risk(obj.uuid_hex, r.uuid_hex, "u1")

        claims = service.list_claims(obj.uuid_hex)
        risks = service.list_risks(obj.uuid_hex)
        assert len(claims) == 1
        assert len(risks) == 1

    def test_typed_exceptions_preserved(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        with pytest.raises(ObjectNotFoundError):
            service.submit_for_review("00000000000000000000000000000000", "u1")
        with pytest.raises(ObjectNotFoundError):
            service.approve("00000000000000000000000000000000", "u1")
        with pytest.raises(ObjectNotFoundError):
            service.reject("00000000000000000000000000000000", "u1", "no")
        with pytest.raises(ObjectNotFoundError):
            service.soft_delete("00000000000000000000000000000000", "u1")


class TestClaimService:
    def test_create_claim(self, repo_session):
        session, repo = repo_session
        service = ClaimService(repo)
        obj, _ = service.create(
            {"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "Test"}, "u1"
        )
        assert obj.object_type == 'claim'

    def test_link_evidence(self, repo_session):
        session, repo = repo_session
        claim_service = ClaimService(repo)
        evidence_service = EvidenceService(repo)

        c, _ = claim_service.create(
            {"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "C1"}, "u1"
        )
        e, _ = evidence_service.create(
            {"evidence_type": "literature_reference", "title": "Study"}, "u1"
        )

        claim_service.link_evidence(c.uuid_hex, e.uuid_hex, "supports_claim")
        relations = repo.list_relations_for_target(c.object_uuid)
        assert len(relations) == 1

    def test_evidence_coverage_check(self, repo_session):
        session, repo = repo_session
        service = ClaimService(repo)
        obj, _ = service.create(
            {"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "C1"}, "u1"
        )
        result = service.check_evidence_coverage(obj.uuid_hex)
        assert result['has_evidence'] is False

    def test_claim_lifecycle(self, repo_session):
        session, repo = repo_session
        service = ClaimService(repo)
        obj, _ = service.create(
            {"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "C1"}, "u1"
        )
        service.submit_for_review(obj.uuid_hex, "u1")
        service.approve(obj.uuid_hex, "u2", "Approved")
        data = service.get_with_payload(obj.uuid_hex)
        assert data['lifecycle_state'] == 'approved'

    def test_typed_exceptions(self, repo_session):
        session, repo = repo_session
        service = ClaimService(repo)
        with pytest.raises(ObjectNotFoundError):
            service.link_evidence("00000000000000000000000000000000",
                                  "00000000000000000000000000000000")


class TestEvidenceService:
    def test_create_evidence(self, repo_session):
        session, repo = repo_session
        service = EvidenceService(repo)
        obj, _ = service.create(
            {"evidence_type": "literature_reference", "title": "Study"}, "u1"
        )
        assert obj.object_type == 'evidence'

    def test_list_evidence(self, repo_session):
        session, repo = repo_session
        service = EvidenceService(repo)
        service.create({"evidence_type": "literature_reference", "title": "S1"}, "u1")
        service.create({"evidence_type": "clinical_data", "title": "S2"}, "u2")
        assert len(service.list()) == 2

    def test_evidence_lifecycle(self, repo_session):
        session, repo = repo_session
        service = EvidenceService(repo)
        obj, _ = service.create(
            {"evidence_type": "literature_reference", "title": "S1"}, "u1"
        )
        service.submit_for_review(obj.uuid_hex, "u1")
        service.approve(obj.uuid_hex, "u2")
        data = service.get_with_payload(obj.uuid_hex)
        assert data['lifecycle_state'] == 'approved'
"""Tests for domain services — Product, Claim, Evidence."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.services import ProductService, ClaimService, EvidenceService


@pytest.fixture
def repo_session():
    """Create an in-memory SQLite session and repo for testing."""
    engine = create_engine("sqlite://", echo=False)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
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


class TestProductService:
    """Tests for ProductService."""

    def test_create_product(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        obj, version = service.create(
            payload={
                "product_id": "PROD-001",
                "name": "Test IVD Kit",
                "description": "A test product",
                "basic_udi_di": "04250710612345",
                "gmdn_code": "12345",
                "manufacturer_name": "Test Corp",
            },
            owner_user_id="user-001",
        )
        session.commit()

        assert obj.object_type == 'product'
        assert obj.lifecycle_state == 'draft'

        # Retrieve via service
        data = service.get_with_payload(obj.uuid_hex)
        assert data is not None
        assert data['payload']['product_id'] == 'PROD-001'
        assert data['payload']['name'] == 'Test IVD Kit'

    def test_list_products(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        service.create({"product_id": "P1", "name": "Product 1"}, "u1")
        service.create({"product_id": "P2", "name": "Product 2"}, "u2")
        session.commit()

        products = service.list()
        assert len(products) == 2

    def test_submit_and_approve_product(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        obj, _ = service.create({"product_id": "P1", "name": "Product 1"}, "u1")
        session.commit()

        assert service.submit_for_review(obj.uuid_hex, "u1") is True
        assert service.approve(obj.uuid_hex, "u2", "Approved") is True

        data = service.get_with_payload(obj.uuid_hex)
        assert data['lifecycle_state'] == 'approved'

    def test_soft_delete_product(self, repo_session):
        session, repo = repo_session
        service = ProductService(repo)
        obj, _ = service.create({"product_id": "P1", "name": "Product 1"}, "u1")
        session.commit()

        assert service.soft_delete(obj.uuid_hex, "u1") is True
        assert service.get(obj.uuid_hex) is None


class TestClaimService:
    """Tests for ClaimService."""

    def test_create_claim(self, repo_session):
        session, repo = repo_session
        service = ClaimService(repo)
        obj, version = service.create(
            payload={
                "claim_type": "performance",
                "jurisdiction": "EU",
                "language": "en",
                "wording": "The device detects SARS-CoV-2 with 95% sensitivity",
            },
            owner_user_id="user-001",
        )
        session.commit()

        assert obj.object_type == 'claim'
        data = service.get_with_payload(obj.uuid_hex)
        assert data['payload']['wording'] == 'The device detects SARS-CoV-2 with 95% sensitivity'

    def test_link_evidence(self, repo_session):
        session, repo = repo_session
        claim_service = ClaimService(repo)
        evidence_service = EvidenceService(repo)

        # Create a claim
        claim_obj, _ = claim_service.create(
            payload={"claim_type": "performance", "jurisdiction": "EU", "language": "en", "wording": "Test claim"},
            owner_user_id="u1",
        )
        # Create evidence
        ev_obj, _ = evidence_service.create(
            payload={"evidence_type": "literature_reference", "title": "Study 2024", "author": "Smith et al."},
            owner_user_id="u1",
        )
        session.commit()

        # Link evidence to claim
        result = claim_service.link_evidence(claim_obj.uuid_hex, ev_obj.uuid_hex)
        assert result is True

        # Verify the link via object_relation
        relations = repo.list_relations_for_target(claim_obj.object_uuid)
        assert len(relations) == 1
        assert relations[0].relation_type == 'supports_claim'
        assert relations[0].source_uuid == ev_obj.object_uuid

    def test_evidence_coverage_check(self, repo_session):
        session, repo = repo_session
        service = ClaimService(repo)
        obj, _ = service.create(
            payload={"claim_type": "safety", "jurisdiction": "EU", "language": "en", "wording": "Safe device"},
            owner_user_id="u1",
        )
        session.commit()

        # No evidence linked
        result = service.check_evidence_coverage(obj.uuid_hex)
        assert result['has_evidence'] is False
        assert result['approvable'] is False

    def test_claim_lifecycle(self, repo_session):
        session, repo = repo_session
        service = ClaimService(repo)
        obj, _ = service.create(
            payload={"claim_type": "clinical", "jurisdiction": "EU", "language": "en", "wording": "Clinical claim"},
            owner_user_id="u1",
        )
        session.commit()

        assert service.submit_for_review(obj.uuid_hex, "u1") is True
        assert service.approve(obj.uuid_hex, "u2", "Approved") is True

        data = service.get_with_payload(obj.uuid_hex)
        assert data['lifecycle_state'] == 'approved'


class TestEvidenceService:
    """Tests for EvidenceService."""

    def test_create_evidence(self, repo_session):
        session, repo = repo_session
        service = EvidenceService(repo)
        obj, version = service.create(
            payload={
                "evidence_type": "literature_reference",
                "title": "Clinical Study 2024",
                "author": "Smith et al.",
                "source_reference": "PMID:12345678",
                "journal": "Journal of Clinical Virology",
            },
            owner_user_id="user-001",
        )
        session.commit()

        assert obj.object_type == 'evidence'
        data = service.get_with_payload(obj.uuid_hex)
        assert data['payload']['title'] == 'Clinical Study 2024'
        assert data['payload']['source_reference'] == 'PMID:12345678'

    def test_list_evidence(self, repo_session):
        session, repo = repo_session
        service = EvidenceService(repo)
        service.create({"evidence_type": "literature_reference", "title": "Study 1"}, "u1")
        service.create({"evidence_type": "clinical_data", "title": "Study 2"}, "u2")
        session.commit()

        items = service.list()
        assert len(items) == 2

    def test_evidence_lifecycle(self, repo_session):
        session, repo = repo_session
        service = EvidenceService(repo)
        obj, _ = service.create(
            payload={"evidence_type": "standards_reference", "title": "ISO 14971"},
            owner_user_id="u1",
        )
        session.commit()

        assert service.submit_for_review(obj.uuid_hex, "u1") is True
        assert service.approve(obj.uuid_hex, "u2", "Valid standard") is True

        data = service.get_with_payload(obj.uuid_hex)
        assert data['lifecycle_state'] == 'approved'
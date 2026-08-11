"""Payload-integrity regressions for graph impact analysis models."""

from copy import deepcopy

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.graph_impact_models import ImpactAnalysis
from orkp.domain.graph_service import GraphProjectionService


@pytest.fixture
def impact_payload():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RegulatoryObjectRepository(session)
        product, _ = repo.create_object(
            "product", {"product_id": "P-INTEGRITY"}, "owner", "owner"
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
                "wording": "Integrity claim",
                "regulatory_scope": [],
            },
            "claim-owner",
            "claim-owner",
        )
        evidence, _ = repo.create_object(
            "evidence",
            {"evidence_type": "literature", "title": "Integrity evidence"},
            "evidence-owner",
            "evidence-owner",
        )
        repo.create_relation(
            product.object_uuid, 1, claim.object_uuid, 1, "has_claim", "owner"
        )
        repo.create_relation(
            evidence.object_uuid, 1, claim.object_uuid, 1, "supported_by", "owner"
        )
        session.commit()
        return (
            GraphProjectionService(repo)
            .impact_analysis(product.uuid_hex, 1, depth=2)
            .model_dump(mode="json")
        )


def test_impact_payload_rejects_path_not_starting_at_changed_root(impact_payload):
    payload = deepcopy(impact_payload)
    target = next(item for item in payload["impacted"] if item["distance"] == 2)
    target["path"][0] = target["path"][1]

    with pytest.raises(ValidationError, match="start at changed root"):
        ImpactAnalysis(**payload)


def test_impact_payload_rejects_unknown_relation_in_path(impact_payload):
    payload = deepcopy(impact_payload)
    target = next(item for item in payload["impacted"] if item["distance"] == 2)
    target["relation_path"][0] = "00000000-0000-0000-0000-000000000001"

    with pytest.raises(ValidationError, match="unknown edge"):
        ImpactAnalysis(**payload)


def test_impact_payload_rejects_edge_that_does_not_connect_path_hop(impact_payload):
    payload = deepcopy(impact_payload)
    target = next(item for item in payload["impacted"] if item["distance"] == 2)
    target["relation_path"].reverse()

    with pytest.raises(ValidationError, match="does not connect adjacent path nodes"):
        ImpactAnalysis(**payload)


def test_impact_payload_rejects_edge_endpoint_outside_declared_nodes(impact_payload):
    payload = deepcopy(impact_payload)
    payload["edges"][0]["target"] = {
        "object_uuid": "00000000-0000-0000-0000-000000000002",
        "object_version": 1,
    }

    with pytest.raises(ValidationError, match="endpoints must be present"):
        ImpactAnalysis(**payload)

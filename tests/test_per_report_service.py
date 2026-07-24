"""Tests for deterministic baseline-pinned PER report generation."""

import json

import pytest

from orkp.domain.exceptions import BaselineValidationError, ImmutableVersionError
from orkp.domain.per_report_service import PERReportService


def _approve(repo, obj, actor="reviewer"):
    repo.transition_state(obj.object_uuid, "in_review", actor)
    repo.transition_state(obj.object_uuid, "approved", actor)


def _create_approved_product(repo):
    product, _ = repo.create_object(
        object_type="product",
        payload={
            "product_id": "P-001",
            "name": "Example IVD",
            "product_kind": "assay",
            "legal_manufacturer": "Example Manufacturer",
            "intended_purpose": "Qualitative detection of an analyte.",
            "regulatory_status": "marketed",
            "specimen_types": [],
            "applicable_regulations": [],
        },
        owner_user_id="author",
        created_by="author",
    )
    _approve(repo, product)
    return product


def test_generate_per_is_baseline_pinned_and_deterministic(repo):
    product = _create_approved_product(repo)
    claim, _ = repo.create_object(
        object_type="claim",
        payload={"wording": "Approved performance claim"},
        owner_user_id="author",
        created_by="author",
    )
    _approve(repo, claim)
    evidence, _ = repo.create_object(
        object_type="evidence",
        payload={"title": "Approved study", "evidence_type": "clinical_study"},
        owner_user_id="author",
        created_by="author",
    )
    _approve(repo, evidence)

    baseline = repo.create_baseline(
        name="PER baseline",
        description=None,
        object_versions=[
            (product.object_uuid, product.current_version),
            (claim.object_uuid, claim.current_version),
            (evidence.object_uuid, evidence.current_version),
        ],
        created_by="author",
    )
    repo.session.commit()

    service = PERReportService(repo)
    first = service.generate(
        product.uuid_hex, baseline.uuid_hex, "PER", "regulatory-author"
    )
    second = service.generate(
        product.uuid_hex, baseline.uuid_hex, "PER", "regulatory-author"
    )

    first_json = service.canonical_json(first.report_uuid)
    second_json = service.canonical_json(second.report_uuid)
    assert first_json == second_json
    assert json.loads(first_json)["baseline_uuid"] == baseline.uuid_hex
    assert len(first.payload.sections) == 10
    assert all(
        entry.version_status == "approved" for entry in first.payload.traceability
    )
    assert {block.provenance for section in first.payload.sections for block in section.blocks} <= {
        "approved",
        "system_generated",
    }


def test_generation_requires_approved_product_version_in_baseline(repo):
    product, _ = repo.create_object(
        object_type="product",
        payload={"name": "Draft product"},
        owner_user_id="author",
        created_by="author",
    )
    baseline = repo.create_baseline(
        name="Draft baseline",
        description=None,
        object_versions=[(product.object_uuid, product.current_version)],
        created_by="author",
    )
    repo.session.commit()

    with pytest.raises(BaselineValidationError):
        PERReportService(repo).generate(
            product.uuid_hex, baseline.uuid_hex, "PER", "regulatory-author"
        )


def test_approved_per_report_is_immutable(repo):
    product = _create_approved_product(repo)
    baseline = repo.create_baseline(
        name="Minimal baseline",
        description=None,
        object_versions=[(product.object_uuid, product.current_version)],
        created_by="author",
    )
    repo.session.commit()

    response = PERReportService(repo).generate(
        product.uuid_hex, baseline.uuid_hex, "PER", "regulatory-author"
    )
    report = repo.get_by_uuid_hex(response.report_uuid)
    _approve(repo, report)
    repo.session.commit()

    with pytest.raises(ImmutableVersionError):
        repo.create_version(
            report.object_uuid,
            response.payload.model_dump(mode="json"),
            "regulatory-author",
        )

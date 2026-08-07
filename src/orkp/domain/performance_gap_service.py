"""Product-scoped Performance Claim evidence-gap aggregation."""

from uuid import UUID

from pydantic import ValidationError

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.evidence_policy import default_evidence_policy
from orkp.domain.exceptions import (
    InvalidPersistedPayloadError,
    ObjectNotFoundError,
    ObjectTypeMismatchError,
)
from orkp.domain.models import ClaimPayload
from orkp.domain.performance_gap_models import (
    PERFORMANCE_CLAIM_TYPES,
    PerformanceClaimGapFinding,
    PerformanceClaimGapItem,
    PerformanceClaimGapReport,
)
from orkp.domain.services import ClaimService


class PerformanceClaimGapService:
    """Identify current Product Performance Claims with insufficient Evidence."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def evaluate_product(self, product_hex: str) -> PerformanceClaimGapReport:
        product = self.repo.get_by_uuid_hex(product_hex)
        if product is None:
            raise ObjectNotFoundError(f"Product {product_hex} not found")
        if product.object_type != "product":
            raise ObjectTypeMismatchError(
                f"Expected product, got '{product.object_type}'"
            )

        product_relations = [
            relation
            for relation in self.repo.list_active_relations_for_source(
                product.object_uuid
            )
            if relation.relation_type == "has_claim"
        ]
        relations_by_claim: dict[bytes, list] = {}
        for relation in product_relations:
            relations_by_claim.setdefault(relation.target_uuid, []).append(relation)

        claim_service = ClaimService(self.repo)
        policy = default_evidence_policy()
        items: list[PerformanceClaimGapItem] = []

        for claim_uuid in sorted(relations_by_claim, key=lambda value: value.hex()):
            claim = self.repo.get_by_uuid(claim_uuid)
            if claim is None:
                raise ObjectNotFoundError(
                    f"Claim {UUID(bytes=claim_uuid).hex} referenced by Product not found"
                )
            version = self.repo.get_version(claim_uuid, claim.current_version)
            if version is None:
                raise ObjectNotFoundError(
                    f"Claim {claim.uuid_hex} version {claim.current_version} not found"
                )
            try:
                payload = ClaimPayload(**(version.payload_json or {}))
            except ValidationError as exc:
                raise InvalidPersistedPayloadError(
                    f"Stored Claim {claim.uuid_hex} payload is invalid"
                ) from exc
            if payload.claim_type not in PERFORMANCE_CLAIM_TYPES:
                continue

            findings: list[PerformanceClaimGapFinding] = []
            claim_links = relations_by_claim[claim_uuid]
            exact_claim_link = any(
                relation.source_version == product.current_version
                and relation.target_version == claim.current_version
                for relation in claim_links
            )
            if not exact_claim_link:
                findings.append(
                    PerformanceClaimGapFinding(
                        rule_code="PERF-CLAIM-LINK-STALE-001",
                        message=(
                            "Product to Claim relation is not pinned to the current "
                            "Product and Claim versions"
                        ),
                    )
                )

            assessment = claim_service.get_approval_assessment(claim.uuid_hex)
            claim_relations = self.repo.list_active_relations_for_target(
                claim.object_uuid
            )
            exact_support = [
                relation
                for relation in claim_relations
                if relation.relation_type == "supported_by"
                and relation.target_version == claim.current_version
            ]
            exact_contradictions = [
                relation
                for relation in claim_relations
                if relation.relation_type == "contradicted_by"
                and relation.target_version == claim.current_version
            ]

            if not exact_support:
                findings.append(
                    PerformanceClaimGapFinding(
                        rule_code="PERF-EVID-MISSING-001",
                        message=(
                            "No active supporting Evidence is linked to the current "
                            "Claim version"
                        ),
                    )
                )
            else:
                support_by_key = {
                    (
                        UUID(item["evidence_uuid"]).bytes,
                        item["evidence_version"],
                    ): item
                    for item in assessment["supporting_evidence"]
                }
                required_quality = policy.get_min_quality_for_severity(payload.severity)
                allowed_types = set(policy.get_allowed_evidence_types(payload.claim_type))
                has_allowed_approved_type = False

                for relation in exact_support:
                    evidence_ref = {
                        "object_uuid": UUID(bytes=relation.source_uuid).hex,
                        "object_version": relation.source_version,
                    }
                    evidence = support_by_key.get(
                        (relation.source_uuid, relation.source_version)
                    )
                    if evidence is None:
                        findings.append(
                            PerformanceClaimGapFinding(
                                rule_code="PERF-EVID-UNAPPROVED-001",
                                message="Supporting Evidence could not be resolved",
                                evidence=evidence_ref,
                            )
                        )
                        continue

                    lifecycle_state = evidence["evidence_lifecycle_state"]
                    version_status = evidence["evidence_version_status"]
                    if lifecycle_state in {"deleted", "obsolete"} or version_status != "approved":
                        findings.append(
                            PerformanceClaimGapFinding(
                                rule_code="PERF-EVID-UNAPPROVED-001",
                                message=(
                                    "Supporting Evidence is not an approved usable version "
                                    f"(lifecycle={lifecycle_state}, status={version_status})"
                                ),
                                evidence=evidence_ref,
                            )
                        )
                        continue

                    evidence_type = evidence["evidence_type"]
                    if evidence_type in allowed_types:
                        has_allowed_approved_type = True

                    quality = evidence["quality_rating"]
                    if not policy.quality_meets_threshold(quality, required_quality):
                        findings.append(
                            PerformanceClaimGapFinding(
                                rule_code="PERF-EVID-QUALITY-001",
                                message=(
                                    f"Evidence quality '{quality}' is below required "
                                    f"'{required_quality}'"
                                ),
                                evidence=evidence_ref,
                            )
                        )

                if not has_allowed_approved_type:
                    findings.append(
                        PerformanceClaimGapFinding(
                            rule_code="PERF-EVID-TYPE-001",
                            message=(
                                "No approved supporting Evidence has an allowed type for "
                                f"'{payload.claim_type}' Claims"
                            ),
                        )
                    )

            for relation in exact_contradictions:
                findings.append(
                    PerformanceClaimGapFinding(
                        rule_code="PERF-EVID-CONTRADICTION-001",
                        message="Active contradictory Evidence exists for the current Claim version",
                        evidence={
                            "object_uuid": UUID(bytes=relation.source_uuid).hex,
                            "object_version": relation.source_version,
                        },
                    )
                )

            findings = sorted(
                findings,
                key=lambda finding: (
                    finding.rule_code,
                    finding.evidence.object_uuid if finding.evidence else "",
                    finding.evidence.object_version if finding.evidence else 0,
                ),
            )
            items.append(
                PerformanceClaimGapItem(
                    claim={
                        "object_uuid": claim.uuid_hex,
                        "object_version": claim.current_version,
                    },
                    claim_type=payload.claim_type,
                    wording=payload.wording,
                    sufficient=not findings,
                    supporting_evidence_count=len(exact_support),
                    findings=findings,
                )
            )

        items = sorted(items, key=lambda item: item.claim.object_uuid)
        sufficient_count = sum(item.sufficient for item in items)
        gap_count = len(items) - sufficient_count
        return PerformanceClaimGapReport(
            product={
                "object_uuid": product.uuid_hex,
                "object_version": product.current_version,
            },
            performance_claim_count=len(items),
            sufficient_claim_count=sufficient_count,
            gap_claim_count=gap_count,
            complete=gap_count == 0,
            claims=items,
        )

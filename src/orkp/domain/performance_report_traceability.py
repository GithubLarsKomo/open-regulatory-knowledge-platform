"""Exact graph validation for Performance Results selected into PER baselines."""

from uuid import UUID

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import BaselineValidationError
from orkp.domain.performance_result_models import PerformanceResultPayload


_ROLE_BY_SOURCE_KIND = {
    "source_data": "statistical_source_data",
    "validated_report": "validated_study_report",
}


def validate_performance_result_traceability(
    repo: RegulatoryObjectRepository,
    result_uuid: bytes,
    result_version: int,
    payload: PerformanceResultPayload,
) -> None:
    """Require the exact canonical Result→Study/Claim/source graph."""
    relations = [
        relation
        for relation in repo.list_active_relations_for_source(result_uuid)
        if relation.source_version == result_version
    ]

    if not _has_relation(
        relations,
        "derived_from",
        payload.study.object_uuid,
        payload.study.object_version,
        role="performance_result_source",
    ):
        raise BaselineValidationError(
            "PER baseline requires exact Performance Result to Study provenance"
        )

    for claim in payload.claims:
        if not _has_relation(
            relations,
            "supported_by",
            claim.object_uuid,
            claim.object_version,
        ):
            raise BaselineValidationError(
                "PER baseline requires exact Performance Result to Claim support"
            )

    for source in payload.statistical_sources:
        if not _has_relation(
            relations,
            "derived_from",
            source.evidence.object_uuid,
            source.evidence.object_version,
            role=_ROLE_BY_SOURCE_KIND[source.source_kind],
        ):
            raise BaselineValidationError(
                "PER baseline requires exact statistical source provenance"
            )


def _has_relation(
    relations,
    relation_type: str,
    target_uuid_hex: str,
    target_version: int,
    role: str | None = None,
) -> bool:
    target_uuid = UUID(target_uuid_hex).bytes
    for relation in relations:
        if relation.relation_type != relation_type:
            continue
        if relation.target_uuid != target_uuid or relation.target_version != target_version:
            continue
        if role is not None and (relation.properties or {}).get("role") != role:
            continue
        return True
    return False

"""Version-pinned hazard-chain traceability evaluation for Risk approval."""

from dataclasses import dataclass

from orkp.db.repository import RegulatoryObjectRepository


@dataclass(frozen=True)
class HazardTraceabilityResult:
    """Aggregate pass/fail state across every current linked Hazard chain."""

    has_hazard: bool
    has_sequence: bool
    has_situation: bool
    has_harm: bool
    has_estimation: bool


def evaluate_hazard_traceability(
    repo: RegulatoryObjectRepository,
    risk_analysis,
    current_outgoing: list,
) -> HazardTraceabilityResult:
    """Require every current Hazard branch to be complete and version-current."""
    hazard_relations = [
        relation
        for relation in current_outgoing
        if relation.relation_type == "has_hazard"
    ]
    if not hazard_relations:
        return HazardTraceabilityResult(False, False, False, False, False)

    has_hazard = True
    has_sequence = True
    has_situation = True
    has_harm = True
    has_estimation = True

    estimation_relations = [
        relation
        for relation in current_outgoing
        if relation.relation_type == "estimated_for"
    ]

    for hazard_relation in hazard_relations:
        hazard = _current_target(repo, hazard_relation, "hazard")
        if hazard is None:
            has_hazard = False
            has_sequence = False
            has_situation = False
            has_harm = False
            has_estimation = False
            continue

        sequence_relations = _relations_from_exact_version(
            repo,
            hazard.object_uuid,
            hazard_relation.target_version,
            "followed_by",
        )
        if not sequence_relations:
            has_sequence = False
            has_situation = False
            has_harm = False
            has_estimation = False
            continue

        for sequence_relation in sequence_relations:
            sequence = _current_target(repo, sequence_relation, "sequence_of_events")
            if sequence is None:
                has_sequence = False
                has_situation = False
                has_harm = False
                has_estimation = False
                continue

            situation_relations = _relations_from_exact_version(
                repo,
                sequence.object_uuid,
                sequence_relation.target_version,
                "creates_situation",
            )
            if not situation_relations:
                has_situation = False
                has_harm = False
                has_estimation = False
                continue

            for situation_relation in situation_relations:
                situation = _current_target(
                    repo,
                    situation_relation,
                    "hazardous_situation",
                )
                if situation is None:
                    has_situation = False
                    has_harm = False
                    has_estimation = False
                    continue

                harm_relations = _relations_from_exact_version(
                    repo,
                    situation.object_uuid,
                    situation_relation.target_version,
                    "may_cause",
                )
                if not harm_relations or any(
                    _current_target(repo, harm_relation, "harm") is None
                    for harm_relation in harm_relations
                ):
                    has_harm = False

                if not any(
                    relation.target_uuid == situation.object_uuid
                    and relation.target_version == situation_relation.target_version
                    for relation in estimation_relations
                ):
                    has_estimation = False

    return HazardTraceabilityResult(
        has_hazard=has_hazard,
        has_sequence=has_sequence,
        has_situation=has_situation,
        has_harm=has_harm,
        has_estimation=has_estimation,
    )


def _relations_from_exact_version(
    repo: RegulatoryObjectRepository,
    source_uuid: bytes,
    source_version: int,
    relation_type: str,
) -> list:
    return [
        relation
        for relation in repo.list_active_relations_for_source(source_uuid)
        if relation.relation_type == relation_type
        and relation.source_version == source_version
    ]


def _current_target(repo: RegulatoryObjectRepository, relation, expected_type: str):
    target = repo.get_by_uuid(relation.target_uuid)
    if (
        target is None
        or target.object_type != expected_type
        or target.current_version != relation.target_version
    ):
        return None
    return target

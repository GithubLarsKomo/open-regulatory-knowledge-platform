"""Read-side queries for version-pinned control verifications."""

from uuid import UUID

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.control_verification_service import ControlVerificationService
from orkp.domain.exceptions import InvalidObjectIdentifierError, ObjectNotFoundError
from orkp.domain.risk_models import ControlVerificationResponse
from orkp.domain.versioned_loader import load_versioned_object


def list_control_verifications_for_risk_analysis(
    repo: RegulatoryObjectRepository,
    risk_analysis_hex: str,
) -> list[ControlVerificationResponse]:
    """Return active verifications linked to a risk analysis, version-pinned."""
    try:
        normalized = UUID(risk_analysis_hex).hex
    except (ValueError, TypeError, AttributeError) as exc:
        raise InvalidObjectIdentifierError(
            f"Invalid UUID format: {risk_analysis_hex}"
        ) from exc

    risk_analysis_obj = repo.get_by_uuid_hex(normalized)
    if risk_analysis_obj is None:
        raise ObjectNotFoundError(f"Risk analysis {normalized} not found")

    risk_analysis = load_versioned_object(
        repo,
        normalized,
        risk_analysis_obj.current_version,
        "risk_analysis",
    )
    service = ControlVerificationService(repo)
    responses: list[ControlVerificationResponse] = []
    seen: set[tuple[bytes, int]] = set()

    for relation in repo.list_active_relations_for_target(
        risk_analysis.object.object_uuid
    ):
        if relation.relation_type != "derived_from":
            continue
        if not relation.properties or relation.properties.get("role") != "verifies_control_for":
            continue
        key = (relation.source_uuid, relation.source_version)
        if key in seen:
            continue
        seen.add(key)
        responses.append(
            service.get_verification(
                UUID(bytes=relation.source_uuid).hex,
                relation.source_version,
            )
        )

    return responses

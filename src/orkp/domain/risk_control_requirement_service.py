"""Version-pinned Risk Control to Requirement traceability."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    InvalidObjectIdentifierError,
    ObjectNotFoundError,
    ObjectTypeMismatchError,
)
from orkp.domain.risk_models import VersionedObjectReference


class RiskControlRequirementLinkResponse(BaseModel):
    """Exact-version traceability link between a Risk Control and Requirement."""

    model_config = ConfigDict(extra="forbid")
    risk_control: VersionedObjectReference
    requirement: VersionedObjectReference
    relation_type: Literal["implements_requirement"] = "implements_requirement"


class RiskControlRequirementService:
    """Create exact current-version Risk Control requirement links."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def link_requirement(
        self,
        risk_control_hex: str,
        requirement_hex: str,
        actor_user_id: str,
    ) -> RiskControlRequirementLinkResponse:
        control = self._load_current(risk_control_hex, "risk_control")
        requirement = self._load_current(requirement_hex, "requirement")

        try:
            self.repo.create_relation(
                source_uuid=control.object_uuid,
                source_version=control.current_version,
                target_uuid=requirement.object_uuid,
                target_version=requirement.current_version,
                relation_type="implements_requirement",
                created_by=actor_user_id,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return RiskControlRequirementLinkResponse(
            risk_control={
                "object_uuid": control.uuid_hex,
                "object_version": control.current_version,
            },
            requirement={
                "object_uuid": requirement.uuid_hex,
                "object_version": requirement.current_version,
            },
        )

    def _load_current(self, uuid_hex: str, expected_type: str):
        try:
            normalized = UUID(uuid_hex).hex
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidObjectIdentifierError(
                f"Invalid UUID format: {uuid_hex}"
            ) from exc

        obj = self.repo.get_by_uuid_hex(normalized)
        if obj is None:
            raise ObjectNotFoundError(f"Object {normalized} not found")
        if obj.object_type != expected_type:
            raise ObjectTypeMismatchError(
                f"Expected type '{expected_type}', got '{obj.object_type}'"
            )
        return obj

"""
Versioned object loader for ORKP.

Typed, immutable results for loading objects by UUID + exact version
with type and lifecycle validation.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from orkp.db.models import RegulatoryObject, ObjectVersion
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    ObjectTypeMismatchError,
    ObjectVersionNotFoundError,
    InvalidLifecycleStateError,
    InvalidPersistedPayloadError,
)
from orkp.domain.risk_policy import RiskPolicy


@dataclass(frozen=True)
class LoadedVersionedObject:
    """Typed result of loading an object by UUID + exact version."""
    object: RegulatoryObject
    version: ObjectVersion
    payload: dict


@dataclass(frozen=True)
class LoadedRiskPolicyResult:
    """Typed result of loading a persisted RiskPolicy."""
    object: RegulatoryObject
    version: ObjectVersion
    payload: dict
    policy: RiskPolicy
    revision: str


def _validate_uuid(uuid_hex: str) -> str:
    """Validate UUID hex format, return normalized form."""
    import uuid as _uuid
    try:
        u = _uuid.UUID(hex=uuid_hex)
        return u.hex
    except (ValueError, AttributeError):
        raise ObjectNotFoundError(f"Invalid UUID format: {uuid_hex}")


def load_versioned_object(
    repo: RegulatoryObjectRepository,
    uuid_hex: str,
    expected_version: int,
    expected_object_type: str,
    allowed_lifecycle_states: Optional[List[str]] = None,
) -> LoadedVersionedObject:
    """Load a regulatory object by UUID and exact version.

    Args:
        repo: Repository instance.
        uuid_hex: UUID hex string.
        expected_version: Exact object-store version number.
        expected_object_type: Expected object_type value.
        allowed_lifecycle_states: Optional list of allowed lifecycle states.

    Returns:
        LoadedVersionedObject with object, version entity, and payload dict.

    Raises:
        ObjectNotFoundError, ObjectTypeMismatchError,
        ObjectVersionNotFoundError, InvalidLifecycleStateError
    """
    hex_val = _validate_uuid(uuid_hex)

    obj = repo.get_by_uuid_hex(hex_val)
    if obj is None:
        raise ObjectNotFoundError(f"Object {uuid_hex} not found")

    if obj.object_type != expected_object_type:
        raise ObjectTypeMismatchError(
            f"Expected type '{expected_object_type}', got '{obj.object_type}'"
        )

    if allowed_lifecycle_states is not None and obj.lifecycle_state not in allowed_lifecycle_states:
        raise InvalidLifecycleStateError(
            f"Object {uuid_hex} is in state '{obj.lifecycle_state}', "
            f"expected one of: {', '.join(allowed_lifecycle_states)}"
        )

    version = repo.get_version(obj.object_uuid, expected_version)
    if version is None:
        raise ObjectVersionNotFoundError(
            f"Version {expected_version} of object {uuid_hex} not found"
        )

    payload = version.payload_json or {}
    return LoadedVersionedObject(object=obj, version=version, payload=payload)


def load_risk_policy(
    repo: RegulatoryObjectRepository,
    policy_uuid: str,
    policy_object_version: int,
) -> LoadedRiskPolicyResult:
    """Load a persisted RiskPolicy by UUID and exact object-store version.

    Returns:
        LoadedRiskPolicyResult with full typed data.

    Raises:
        ObjectNotFoundError, ObjectTypeMismatchError, ObjectVersionNotFoundError,
        InvalidLifecycleStateError, InvalidPersistedPayloadError.
    """
    from pydantic import ValidationError
    from orkp.domain.risk_models import RiskPolicyPayload

    loaded = load_versioned_object(
        repo, policy_uuid, policy_object_version,
        'risk_policy', allowed_lifecycle_states=['approved', 'effective'],
    )

    # Validate payload with Pydantic
    try:
        validated = RiskPolicyPayload(**loaded.payload)
    except ValidationError as exc:
        raise InvalidPersistedPayloadError(
            f"Risk policy {policy_uuid} v{policy_object_version} payload invalid"
        ) from exc

    # Build RiskPolicy instance — use direct field access, no getattr defaults
    policy = RiskPolicy(
        severity_scale=list(validated.severity_scale),
        probability_scale=list(validated.probability_scale),
        risk_matrix=dict(validated.risk_matrix),
        acceptability_rules=dict(validated.acceptability_rules),
        required_actions=dict(validated.required_actions),
        control_hierarchy=list(validated.control_hierarchy),
        benefit_risk_required_for=list(validated.benefit_risk_required_for),
        version=validated.policy_version,
    )

    return LoadedRiskPolicyResult(
        object=loaded.object,
        version=loaded.version,
        payload=loaded.payload,
        policy=policy,
        revision=validated.policy_version,
    )
"""
Versioned object loader for ORKP.

Provides reusable functions for loading objects by UUID + exact version
with type and lifecycle validation.
"""

import uuid
from typing import Any, Dict, List, Optional, Tuple

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    ObjectTypeMismatchError,
    ObjectVersionNotFoundError,
    InvalidLifecycleStateError,
    InvalidPersistedPayloadError,
)


def load_versioned_object(
    repo: RegulatoryObjectRepository,
    uuid_hex: str,
    expected_version: int,
    expected_object_type: str,
    allowed_lifecycle_states: Optional[List[str]] = None,
) -> Tuple[Any, Dict[str, Any]]:
    """Load a regulatory object by UUID and exact version.

    Args:
        repo: Repository instance.
        uuid_hex: UUID hex string.
        expected_version: Exact object-store version number.
        expected_object_type: Expected object_type value.
        allowed_lifecycle_states: Optional list of allowed lifecycle states.

    Returns:
        Tuple of (regulatory_object, version_payload_dict).

    Raises:
        ObjectNotFoundError: Object not found.
        ObjectTypeMismatchError: Object type does not match.
        ObjectVersionNotFoundError: Specific version not found.
        InvalidLifecycleStateError: Lifecycle state not allowed.
    """
    obj = repo.get_by_uuid_hex(uuid_hex)
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
    return obj, payload


def load_risk_policy(
    repo: RegulatoryObjectRepository,
    policy_uuid: str,
    policy_object_version: int,
) -> Tuple[Any, Dict[str, Any], Any]:
    """Load a persisted RiskPolicy by UUID and exact object-store version.

    Returns:
        Tuple of (policy_object, policy_payload_dict, risk_policy_instance).

    Raises:
        ObjectNotFoundError, ObjectTypeMismatchError, ObjectVersionNotFoundError,
        InvalidLifecycleStateError, InvalidPersistedPayloadError.
    """
    from orkp.domain.risk_models import RiskPolicyPayload
    from orkp.domain.risk_policy import RiskPolicy

    obj, payload = load_versioned_object(
        repo, policy_uuid, policy_object_version,
        'risk_policy', allowed_lifecycle_states=['approved', 'effective'],
    )

    # Validate payload with Pydantic
    try:
        validated = RiskPolicyPayload(**payload)
    except Exception as e:
        raise InvalidPersistedPayloadError(
            f"Risk policy {policy_uuid} v{policy_object_version} payload invalid: {e}"
        )

    # Build RiskPolicy instance
    policy = RiskPolicy(
        severity_scale=list(validated.severity_scale),
        probability_scale=list(validated.probability_scale),
        risk_matrix=dict(validated.risk_matrix),
        acceptability_rules=dict(validated.acceptability_rules),
        required_actions=dict(getattr(validated, 'required_actions', {})),
        control_hierarchy=list(validated.control_hierarchy),
        benefit_risk_required_for=list(getattr(validated, 'benefit_risk_required_for', [])),
        version=validated.policy_version,
    )

    return obj, payload, policy
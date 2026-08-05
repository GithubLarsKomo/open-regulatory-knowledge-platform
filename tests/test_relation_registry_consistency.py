"""Consistency tests for canonical relation registration."""

from orkp.db.models import RELATION_TYPES
from orkp.domain.relation_policy import RELATION_SCHEMA


def test_relation_policy_types_are_registered_in_core():
    """Every canonical relation policy entry must be accepted by the repository."""
    missing = set(RELATION_SCHEMA) - set(RELATION_TYPES)
    assert not missing, (
        f"Relation policy types missing from RELATION_TYPES: {sorted(missing)}"
    )

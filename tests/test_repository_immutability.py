"""Regression tests for the core object-store immutability boundary."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import ImmutableVersionError, ObjectNotFoundError


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _create(repo):
    obj, _ = repo.create_object("claim", {"wording": "v1"}, "owner", "owner")
    return obj


def _approve(repo, obj):
    repo.transition_state(obj.object_uuid, "in_review", "owner")
    repo.transition_state(obj.object_uuid, "approved", "approver")


@pytest.mark.parametrize("state", ["draft", "in_review", "rejected"])
def test_preapproval_states_remain_versionable(repo, state):
    obj = _create(repo)
    if state == "in_review":
        repo.transition_state(obj.object_uuid, "in_review", "owner")
    elif state == "rejected":
        repo.transition_state(obj.object_uuid, "in_review", "owner")
        repo.transition_state(obj.object_uuid, "rejected", "approver")

    version = repo.create_version(obj.object_uuid, {"wording": "v2"}, "owner")

    assert version.version_no == 2
    assert obj.current_version == 2


def test_effective_object_cannot_receive_new_version(repo):
    obj = _create(repo)
    _approve(repo, obj)
    repo.transition_state(obj.object_uuid, "effective", "owner")

    with pytest.raises(ImmutableVersionError, match="effective"):
        repo.create_version(obj.object_uuid, {"wording": "v2"}, "owner")

    assert obj.current_version == 1
    assert len(repo.list_versions(obj.object_uuid)) == 1


def test_obsolete_object_cannot_receive_new_version(repo):
    obj = _create(repo)
    _approve(repo, obj)
    repo.transition_state(obj.object_uuid, "effective", "owner")
    repo.transition_state(obj.object_uuid, "obsolete", "owner")

    with pytest.raises(ImmutableVersionError, match="obsolete"):
        repo.create_version(obj.object_uuid, {"wording": "v2"}, "owner")

    assert obj.current_version == 1
    assert len(repo.list_versions(obj.object_uuid)) == 1


def test_deleted_object_cannot_receive_new_version(repo):
    obj = _create(repo)
    repo.soft_delete(obj.object_uuid, "owner")

    with pytest.raises(ObjectNotFoundError):
        repo.create_version(obj.object_uuid, {"wording": "v2"}, "owner")

    persisted = repo.get_by_uuid_including_deleted(obj.object_uuid)
    assert persisted.current_version == 1
    assert len(repo.list_versions(obj.object_uuid)) == 1

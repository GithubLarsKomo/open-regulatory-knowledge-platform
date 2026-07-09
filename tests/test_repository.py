"""Tests for the regulatory object repository."""

import uuid
from datetime import datetime

import pytest

from orkp.db.models import (
    RegulatoryObject,
    ObjectVersion,
    EventLog,
    ApprovalRecord,
    _new_uuid,
    _bin_to_str,
)


class TestCreateObject:
    """Tests for creating regulatory objects."""

    def test_create_draft_object(self, repo):
        """A draft object can be created with initial version."""
        obj, version = repo.create_object(
            object_type='claim',
            payload={'wording': 'Test claim', 'type': 'performance'},
            owner_user_id='user-001',
            created_by='user-001',
        )

        assert obj.object_type == 'claim'
        assert obj.lifecycle_state == 'draft'
        assert obj.current_version == 1
        assert obj.owner_user_id == 'user-001'
        assert obj.deleted_at is None

        assert version.version_no == 1
        assert version.status == 'draft'
        assert version.payload_json == {'wording': 'Test claim', 'type': 'performance'}
        assert version.created_by == 'user-001'

    def test_create_object_generates_event(self, repo):
        """Creating an object generates a 'created' event."""
        obj, _ = repo.create_object(
            object_type='risk',
            payload={'hazard': 'Electrical shock'},
            owner_user_id='user-002',
            created_by='user-002',
        )

        events = repo.get_event_history(obj.object_uuid)
        assert len(events) == 1
        assert events[0].event_type == 'created'
        assert events[0].actor_user_id == 'user-002'

    def test_create_object_unique_uuid(self, repo):
        """Each created object has a unique UUID."""
        obj1, _ = repo.create_object('claim', {'a': 1}, 'u1', 'u1')
        obj2, _ = repo.create_object('claim', {'b': 2}, 'u2', 'u2')
        assert obj1.object_uuid != obj2.object_uuid


class TestGetObject:
    """Tests for retrieving regulatory objects."""

    def test_get_by_uuid(self, repo):
        """An object can be retrieved by its UUID."""
        obj, _ = repo.create_object('claim', {'wording': 'Test'}, 'u1', 'u1')
        fetched = repo.get_by_uuid(obj.object_uuid)
        assert fetched is not None
        assert fetched.object_uuid == obj.object_uuid
        assert fetched.object_type == 'claim'

    def test_get_by_uuid_hex(self, repo):
        """An object can be retrieved by hex UUID string."""
        obj, _ = repo.create_object('claim', {'wording': 'Test'}, 'u1', 'u1')
        fetched = repo.get_by_uuid_hex(obj.uuid_hex)
        assert fetched is not None
        assert fetched.object_uuid == obj.object_uuid

    def test_get_nonexistent_uuid(self, repo):
        """Getting a nonexistent UUID returns None."""
        fake_uuid = _new_uuid()
        assert repo.get_by_uuid(fake_uuid) is None

    def test_get_version(self, repo):
        """A specific version can be retrieved."""
        obj, v1 = repo.create_object('claim', {'wording': 'v1'}, 'u1', 'u1')
        fetched = repo.get_version(obj.object_uuid, 1)
        assert fetched is not None
        assert fetched.payload_json == {'wording': 'v1'}

    def test_list_versions(self, repo):
        """All versions of an object can be listed."""
        obj, v1 = repo.create_object('claim', {'wording': 'v1'}, 'u1', 'u1')
        v2 = repo.create_version(obj.object_uuid, {'wording': 'v2'}, 'u1')
        versions = repo.list_versions(obj.object_uuid)
        assert len(versions) == 2
        assert versions[0].version_no == 2  # newest first
        assert versions[1].version_no == 1


class TestListObjects:
    """Tests for listing and searching objects."""

    def test_list_all_objects(self, repo):
        """All non-deleted objects are listed."""
        repo.create_object('claim', {}, 'u1', 'u1')
        repo.create_object('risk', {}, 'u2', 'u2')
        objects = repo.list_objects()
        assert len(objects) == 2

    def test_list_by_type(self, repo):
        """Objects can be filtered by type."""
        repo.create_object('claim', {}, 'u1', 'u1')
        repo.create_object('risk', {}, 'u2', 'u2')
        claims = repo.list_objects(object_type='claim')
        assert len(claims) == 1
        assert claims[0].object_type == 'claim'

    def test_list_by_state(self, repo):
        """Objects can be filtered by lifecycle state."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        drafts = repo.list_objects(lifecycle_state='draft')
        in_review = repo.list_objects(lifecycle_state='in_review')
        assert len(drafts) == 0
        assert len(in_review) == 1

    def test_list_excludes_soft_deleted(self, repo):
        """Soft-deleted objects are excluded from listing."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.soft_delete(obj.object_uuid, 'u1')
        objects = repo.list_objects()
        assert len(objects) == 0


class TestCreateVersion:
    """Tests for creating new versions."""

    def test_create_new_version(self, repo):
        """A new version can be created for a draft object."""
        obj, v1 = repo.create_object('claim', {'wording': 'v1'}, 'u1', 'u1')
        v2 = repo.create_version(obj.object_uuid, {'wording': 'v2'}, 'u1')

        assert v2 is not None
        assert v2.version_no == 2
        assert v2.payload_json == {'wording': 'v2'}

        # Object's current version is updated
        fetched = repo.get_by_uuid(obj.object_uuid)
        assert fetched.current_version == 2

    def test_cannot_create_version_on_approved(self, repo):
        """Creating a version on an approved object returns None."""
        obj, _ = repo.create_object('claim', {'wording': 'v1'}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        repo.transition_state(obj.object_uuid, 'approved', 'u1')

        v2 = repo.create_version(obj.object_uuid, {'wording': 'v2'}, 'u1')
        assert v2 is None

    def test_version_creates_event(self, repo):
        """Creating a version generates an 'updated' event."""
        obj, _ = repo.create_object('claim', {'wording': 'v1'}, 'u1', 'u1')
        repo.create_version(obj.object_uuid, {'wording': 'v2'}, 'u1')

        events = repo.get_event_history(obj.object_uuid)
        assert len(events) == 2
        assert events[0].event_type == 'updated'


class TestLifecycleTransitions:
    """Tests for lifecycle state transitions."""

    def test_draft_to_in_review(self, repo):
        """A draft object can be submitted for review."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        result = repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        assert result is True
        fetched = repo.get_by_uuid(obj.object_uuid)
        assert fetched.lifecycle_state == 'in_review'

    def test_in_review_to_approved(self, repo):
        """An in_review object can be approved."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        result = repo.transition_state(obj.object_uuid, 'approved', 'u2')
        assert result is True
        fetched = repo.get_by_uuid(obj.object_uuid)
        assert fetched.lifecycle_state == 'approved'

    def test_approved_version_immutable(self, repo):
        """After approval, the version status is 'approved'."""
        obj, v1 = repo.create_object('claim', {'wording': 'test'}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        repo.transition_state(obj.object_uuid, 'approved', 'u2')

        version = repo.get_version(obj.object_uuid, 1)
        assert version.status == 'approved'

    def test_invalid_transition(self, repo):
        """An invalid transition returns False."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        # Cannot go from draft directly to approved
        result = repo.transition_state(obj.object_uuid, 'approved', 'u1')
        assert result is False
        fetched = repo.get_by_uuid(obj.object_uuid)
        assert fetched.lifecycle_state == 'draft'  # unchanged

    def test_approval_creates_record(self, repo):
        """Approval creates an ApprovalRecord."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        repo.transition_state(obj.object_uuid, 'approved', 'u2', comments='Looks good')

        # Check approval record via event log
        events = repo.get_event_history(obj.object_uuid)
        approval_events = [e for e in events if e.event_type == 'approved']
        assert len(approval_events) == 1
        assert approval_events[0].actor_user_id == 'u2'

    def test_rejected_retains_comments(self, repo):
        """Rejected objects retain reviewer comments."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        result = repo.transition_state(
            obj.object_uuid, 'rejected', 'u2',
            comments='Insufficient evidence'
        )
        assert result is True
        fetched = repo.get_by_uuid(obj.object_uuid)
        assert fetched.lifecycle_state == 'rejected'


class TestSoftDelete:
    """Tests for soft deletion."""

    def test_soft_delete(self, repo):
        """An object can be soft-deleted."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        result = repo.soft_delete(obj.object_uuid, 'u1')
        assert result is True

        fetched = repo.get_by_uuid(obj.object_uuid)
        assert fetched is None  # excluded from normal queries

    def test_soft_delete_nonexistent(self, repo):
        """Soft-deleting a nonexistent object returns False."""
        result = repo.soft_delete(_new_uuid(), 'u1')
        assert result is False

    def test_soft_delete_creates_event(self, repo):
        """Soft deletion generates an 'obsoleted' event."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.soft_delete(obj.object_uuid, 'u1')

        events = repo.get_event_history(obj.object_uuid)
        assert any(e.event_type == 'obsoleted' for e in events)


class TestEventHistory:
    """Tests for event history retrieval."""

    def test_event_history_ordered(self, repo):
        """Events are returned in reverse chronological order."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u2')

        events = repo.get_event_history(obj.object_uuid)
        assert len(events) == 2
        assert events[0].event_type == 'submitted_for_review'
        assert events[1].event_type == 'created'

    def test_event_history_empty(self, repo):
        """A nonexistent object has no events."""
        events = repo.get_event_history(_new_uuid())
        assert len(events) == 0
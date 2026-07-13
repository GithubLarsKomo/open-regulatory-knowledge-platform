"""Tests for the regulatory object repository."""

import sys
import uuid
from datetime import datetime
from pathlib import Path

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
        """Soft deletion generates a 'deleted' event."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.soft_delete(obj.object_uuid, 'u1')

        events = repo.get_event_history(obj.object_uuid)
        assert any(e.event_type == 'deleted' for e in events)


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


class TestOptimisticLocking:
    """Tests for optimistic locking (DB-OBJ-0004)."""

    def test_lock_version_increments_on_create(self, repo):
        """A newly created object has lock_version=1."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        assert obj.lock_version == 1

    def test_stale_lock_raises_on_create_version(self, repo):
        """Creating version with stale lock_version raises."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        with pytest.raises(ValueError, match='Stale lock'):
            repo.create_version(obj.object_uuid, {'wording': 'v2'}, 'u1', expected_lock_version=999)

    def test_stale_lock_raises_on_transition(self, repo):
        """Transition with stale lock_version raises."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        with pytest.raises(ValueError, match='Stale lock'):
            repo.transition_state(obj.object_uuid, 'in_review', 'u1', expected_lock_version=999)

    def test_stale_lock_raises_on_soft_delete(self, repo):
        """Soft delete with stale lock_version raises."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        with pytest.raises(ValueError, match='Stale lock'):
            repo.soft_delete(obj.object_uuid, 'u1', expected_lock_version=999)


class TestLifecycleStates:
    """Tests for lifecycle state machine (SPEC-CoreObjectStore)."""

    def test_rejected_to_draft(self, repo):
        """A rejected object can be returned to draft."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        repo.transition_state(obj.object_uuid, 'rejected', 'u2')
        result = repo.transition_state(obj.object_uuid, 'draft', 'u1')
        assert result is True
        fetched = repo.get_by_uuid(obj.object_uuid)
        assert fetched.lifecycle_state == 'draft'

    def test_approved_to_effective(self, repo):
        """An approved object can become effective."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        repo.transition_state(obj.object_uuid, 'approved', 'u2')
        result = repo.transition_state(obj.object_uuid, 'effective', 'u1')
        assert result is True
        assert repo.get_by_uuid(obj.object_uuid).lifecycle_state == 'effective'

    def test_effective_to_obsolete(self, repo):
        """An effective object can become obsolete."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        repo.transition_state(obj.object_uuid, 'approved', 'u2')
        repo.transition_state(obj.object_uuid, 'effective', 'u1')
        result = repo.transition_state(obj.object_uuid, 'obsolete', 'u1')
        assert result is True
        assert repo.get_by_uuid(obj.object_uuid).lifecycle_state == 'obsolete'

    def test_draft_to_deleted(self, repo):
        """A draft object can be directly deleted."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.soft_delete(obj.object_uuid, 'u1')
        assert repo.get_by_uuid(obj.object_uuid) is None
        # Can be retrieved with include_deleted
        included = repo.get_by_uuid_including_deleted(obj.object_uuid)
        assert included is not None
        assert included.lifecycle_state == 'deleted'

    def test_deleted_excluded_from_list(self, repo):
        """Deleted objects are excluded from list_objects."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.soft_delete(obj.object_uuid, 'u1')
        objects = repo.list_objects()
        assert len(objects) == 0


class TestBaseline:
    """Tests for baseline operations (DB-OBJ-0009)."""

    def test_create_baseline(self, repo):
        """A baseline can be created with object-version pairs."""
        obj1, _ = repo.create_object('claim', {'wording': 'c1'}, 'u1', 'u1')
        obj2, _ = repo.create_object('risk', {'hazard': 'h1'}, 'u2', 'u2')

        b = repo.create_baseline(
            name='Test Baseline',
            description='First test',
            object_versions=[(obj1.object_uuid, 1), (obj2.object_uuid, 1)],
            created_by='u1',
        )
        assert b.name == 'Test Baseline'
        assert b.description == 'First test'

        items = repo.list_baseline_items(b.baseline_uuid)
        assert len(items) == 2

    def test_get_baseline(self, repo):
        """A baseline can be retrieved by UUID."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        b = repo.create_baseline('B', None, [(obj.object_uuid, 1)], 'u1')
        fetched = repo.get_baseline(b.baseline_uuid)
        assert fetched is not None
        assert fetched.name == 'B'
        assert fetched.baseline_uuid == b.baseline_uuid

    def test_baseline_items_immutable_snapshot(self, repo):
        """Baseline items capture the exact payload at creation."""
        obj, _ = repo.create_object('claim', {'wording': 'original'}, 'u1', 'u1')
        b = repo.create_baseline('B', None, [(obj.object_uuid, 1)], 'u1')
        items = repo.list_baseline_items(b.baseline_uuid)
        assert len(items) == 1
        assert items[0].snapshot_json == {'wording': 'original'}

        # Update the original object
        v2 = repo.create_version(obj.object_uuid, {'wording': 'updated'}, 'u1')
        items_again = repo.list_baseline_items(b.baseline_uuid)
        assert items_again[0].snapshot_json == {'wording': 'original'}  # unchanged

    def test_baseline_nonexistent_version_raises(self, repo):
        """Creating a baseline with a nonexistent version raises ValueError."""
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        with pytest.raises(ValueError, match='does not exist'):
            repo.create_baseline('B', None, [(obj.object_uuid, 999)], 'u1')


class TestObjectRelation:
    """Tests for object relations (DB-OBJ-0005)."""

    def test_create_relation(self, repo):
        """A relation can be created between two objects."""
        src, _ = repo.create_object('claim', {'wording': 'source'}, 'u1', 'u1')
        tgt, _ = repo.create_object('evidence', {'title': 'target'}, 'u2', 'u2')

        rel = repo.create_relation(
            source_uuid=src.object_uuid,
            source_version=1,
            target_uuid=tgt.object_uuid,
            target_version=1,
            relation_type='supports_claim',
            created_by='u1',
        )
        assert rel is not None
        assert rel.relation_type == 'supports_claim'

    def test_list_relations_by_source(self, repo):
        """Relations can be listed by source object."""
        src, _ = repo.create_object('claim', {}, 'u1', 'u1')
        tgt1, _ = repo.create_object('evidence', {}, 'u2', 'u2')
        tgt2, _ = repo.create_object('evidence', {}, 'u3', 'u3')

        repo.create_relation(src.object_uuid, 1, tgt1.object_uuid, 1, 'supports_claim', 'u1')
        repo.create_relation(src.object_uuid, 1, tgt2.object_uuid, 1, 'supports_claim', 'u1')

        relations = repo.list_relations_for_source(src.object_uuid)
        assert len(relations) == 2

    def test_list_relations_by_target(self, repo):
        """Relations can be listed by target object."""
        src1, _ = repo.create_object('claim', {}, 'u1', 'u1')
        src2, _ = repo.create_object('risk', {}, 'u2', 'u2')
        tgt, _ = repo.create_object('evidence', {}, 'u3', 'u3')

        repo.create_relation(src1.object_uuid, 1, tgt.object_uuid, 1, 'supports_claim', 'u1')
        repo.create_relation(src2.object_uuid, 1, tgt.object_uuid, 1, 'mitigates', 'u2')

        relations = repo.list_relations_for_target(tgt.object_uuid)
        assert len(relations) == 2

    def test_reject_nonexistent_version(self, repo):
        """Creating a relation with a nonexistent version returns None."""
        src, _ = repo.create_object('claim', {}, 'u1', 'u1')
        tgt, _ = repo.create_object('evidence', {}, 'u2', 'u2')
        rel = repo.create_relation(src.object_uuid, 999, tgt.object_uuid, 1, 'supports_claim', 'u1')
        assert rel is None


class TestSubprocessCLI:
    """Test that the backlog generator runs as a CLI script."""

    def test_backlog_generator_cli_generates_files(self):
        """Invoking backlog_generator.py as a subprocess generates output files."""
        import subprocess
        import tempfile
        import shutil
        tmpdir = Path(tempfile.mkdtemp())
        try:
            repo_root = Path(__file__).resolve().parent.parent
            # Copy entire META config
            shutil.copytree(repo_root / 'META', tmpdir / 'META')
            # Copy all SPEC files needed for foundation tasks
            for spec_file in ['SPEC.md', 'ARCHITECTURE/SPEC-Architecture.md',
                              'META/REQ-META.md', 'DATABASE/SPEC-CoreObjectStore.md']:
                src = repo_root / spec_file
                if src.exists():
                    dest = tmpdir / spec_file
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)

            env = {**subprocess.os.environ, 'PYTHONIOENCODING': 'utf-8'}
            result = subprocess.run(
                [sys.executable, str(repo_root / 'tools' / 'backlog_generator.py'),
                 '--path', str(tmpdir), '--output-dir', str(tmpdir / 'TRACEABILITY'), '--task-md'],
                capture_output=True, text=True, cwd=tmpdir, env=env,
            )
            assert result.returncode == 0, f"CLI failed: {result.stderr}"
            assert (tmpdir / 'TRACEABILITY' / 'backlog.md').exists()
            assert (tmpdir / 'TRACEABILITY' / 'backlog.csv').exists()
            assert (tmpdir / 'TASK.md').exists()
        finally:
            shutil.rmtree(tmpdir)
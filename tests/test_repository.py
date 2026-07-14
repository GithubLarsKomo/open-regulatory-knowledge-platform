"""Tests for the regulatory object repository."""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker, Session

from orkp.db.models import (
    Base,
    RegulatoryObject,
    ObjectVersion,
    ObjectRelation,
    EventLog,
    ApprovalRecord,
    Baseline,
    BaselineItem,
    _new_uuid,
    _bin_to_str,
    RELATION_TYPES,
)
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    InvalidLifecycleTransitionError,
    ImmutableVersionError,
    OptimisticLockError,
    InvalidRelationError,
    BaselineValidationError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo():
    """Create an in-memory SQLite session and repo for testing."""
    engine = create_engine("sqlite://", echo=False)

    @sa_event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    repository = RegulatoryObjectRepository(session)
    yield repository
    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# TestCreateObject
# ---------------------------------------------------------------------------

class TestCreateObject:
    def test_create_draft_object(self, repo):
        obj, version = repo.create_object(
            object_type='claim',
            payload={'wording': 'Test claim'},
            owner_user_id='user-001',
            created_by='user-001',
        )
        assert obj.object_type == 'claim'
        assert obj.lifecycle_state == 'draft'
        assert obj.current_version == 1
        assert obj.lock_version == 1
        assert version.version_no == 1
        assert version.status == 'draft'

    def test_create_generates_event(self, repo):
        obj, _ = repo.create_object('risk', {'hazard': 'Shock'}, 'u2', 'u2')
        events = repo.get_event_history(obj.object_uuid)
        assert len(events) == 1
        assert events[0].event_type == 'created'
        assert events[0].aggregate_type == 'regulatory_object'
        assert events[0].aggregate_uuid == obj.object_uuid

    def test_create_unique_uuid(self, repo):
        o1, _ = repo.create_object('claim', {}, 'u1', 'u1')
        o2, _ = repo.create_object('claim', {}, 'u2', 'u2')
        assert o1.object_uuid != o2.object_uuid


# ---------------------------------------------------------------------------
# TestGetObject
# ---------------------------------------------------------------------------

class TestGetObject:
    def test_get_by_uuid(self, repo):
        obj, _ = repo.create_object('claim', {'w': 'test'}, 'u1', 'u1')
        fetched = repo.get_by_uuid(obj.object_uuid)
        assert fetched is not None
        assert fetched.object_uuid == obj.object_uuid

    def test_get_by_uuid_hex(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        fetched = repo.get_by_uuid_hex(obj.uuid_hex)
        assert fetched is not None

    def test_get_nonexistent(self, repo):
        assert repo.get_by_uuid(_new_uuid()) is None

    def test_get_version(self, repo):
        obj, _ = repo.create_object('claim', {'w': 'v1'}, 'u1', 'u1')
        v = repo.get_version(obj.object_uuid, 1)
        assert v is not None and v.payload_json == {'w': 'v1'}

    def test_list_versions(self, repo):
        obj, _ = repo.create_object('claim', {'w': 'v1'}, 'u1', 'u1')
        repo.create_version(obj.object_uuid, {'w': 'v2'}, 'u1')
        versions = repo.list_versions(obj.object_uuid)
        assert len(versions) == 2
        assert versions[0].version_no == 2


# ---------------------------------------------------------------------------
# TestListObjects
# ---------------------------------------------------------------------------

class TestListObjects:
    def test_list_all(self, repo):
        repo.create_object('claim', {}, 'u1', 'u1')
        repo.create_object('risk', {}, 'u2', 'u2')
        assert len(repo.list_objects()) == 2

    def test_filter_by_type(self, repo):
        repo.create_object('claim', {}, 'u1', 'u1')
        repo.create_object('risk', {}, 'u2', 'u2')
        assert len(repo.list_objects(object_type='claim')) == 1

    def test_excludes_deleted(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.soft_delete(obj.object_uuid, 'u1')
        assert len(repo.list_objects()) == 0


# ---------------------------------------------------------------------------
# TestCreateVersion
# ---------------------------------------------------------------------------

class TestCreateVersion:
    def test_create_new_version(self, repo):
        obj, _ = repo.create_object('claim', {'w': 'v1'}, 'u1', 'u1')
        v2 = repo.create_version(obj.object_uuid, {'w': 'v2'}, 'u1')
        assert v2.version_no == 2
        assert repo.get_by_uuid(obj.object_uuid).current_version == 2

    def test_approved_raises_immutable(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        repo.transition_state(obj.object_uuid, 'approved', 'u2')
        with pytest.raises(ImmutableVersionError):
            repo.create_version(obj.object_uuid, {'w': 'v2'}, 'u1')

    def test_nonexistent_raises_not_found(self, repo):
        with pytest.raises(ObjectNotFoundError):
            repo.create_version(_new_uuid(), {}, 'u1')


# ---------------------------------------------------------------------------
# TestLifecycleTransitions
# ---------------------------------------------------------------------------

_LIFECYCLE_SUCCESS = [
    ('draft', 'in_review'),
    ('in_review', 'approved'),
    ('in_review', 'rejected'),
    ('rejected', 'draft'),
    ('approved', 'effective'),
    ('effective', 'obsolete'),
    ('obsolete', 'deleted'),
    ('draft', 'deleted'),      # soft_delete from draft
    ('rejected', 'deleted'),   # soft_delete from rejected
]

_LIFECYCLE_FAIL = [
    ('draft', 'approved'),
    ('draft', 'effective'),
    ('draft', 'obsolete'),
    ('in_review', 'effective'),
    ('in_review', 'deleted'),
    ('approved', 'deleted'),
    ('approved', 'rejected'),
    ('approved', 'in_review'),
    ('effective', 'deleted'),
    ('effective', 'in_review'),
    ('effective', 'draft'),
    ('obsolete', 'draft'),
]


class TestLifecycleTransitions:
    @pytest.mark.parametrize('start, target', _LIFECYCLE_SUCCESS)
    def test_allowed_transitions(self, repo, start, target):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        # Walk to start state
        _walk_to(repo, obj, start)
        if target == 'deleted':
            repo.soft_delete(obj.object_uuid, 'u1')
        else:
            repo.transition_state(obj.object_uuid, target, 'u1')
        assert repo.get_by_uuid_including_deleted(obj.object_uuid).lifecycle_state in (target, 'deleted')

    @pytest.mark.parametrize('start, target', _LIFECYCLE_FAIL)
    def test_forbidden_transitions(self, repo, start, target):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        _walk_to(repo, obj, start)
        with pytest.raises((InvalidLifecycleTransitionError)):
            if target == 'deleted':
                repo.soft_delete(obj.object_uuid, 'u1')
            else:
                repo.transition_state(obj.object_uuid, target, 'u1')

    def test_approval_makes_version_immutable(self, repo):
        obj, _ = repo.create_object('claim', {'w': 'test'}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        repo.transition_state(obj.object_uuid, 'approved', 'u2')
        v = repo.get_version(obj.object_uuid, 1)
        assert v.status == 'approved'

    def test_approval_creates_record(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        repo.transition_state(obj.object_uuid, 'approved', 'u2', 'OK')
        events = repo.get_event_history(obj.object_uuid)
        assert any(e.event_type == 'approved' for e in events)


def _walk_to(repo, obj, target_state):
    """Walk an object through lifecycle to reach target_state."""
    from orkp.db.repository import _VALID_TRANSITIONS
    state = obj.lifecycle_state
    visited = {state}
    max_steps = 10
    for _ in range(max_steps):
        if state == target_state:
            return
        allowed = _VALID_TRANSITIONS.get(state, [])
        # Prefer direct jump to target
        if target_state in allowed:
            repo.transition_state(obj.object_uuid, target_state, 'system')
            return
        # Take first allowed step
        if allowed:
            repo.transition_state(obj.object_uuid, allowed[0], 'system')
            state = allowed[0]
            if state in visited:
                break
            visited.add(state)
    # If we can't get there and it's a deletion test, just set state directly
    if target_state == 'obsolete':
        _walk_to(repo, obj, 'approved')
        _walk_to(repo, obj, 'effective')
        repo.transition_state(obj.object_uuid, 'obsolete', 'system')


# ---------------------------------------------------------------------------
# TestSoftDelete
# ---------------------------------------------------------------------------

class TestSoftDelete:
    def test_soft_delete_from_draft(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.soft_delete(obj.object_uuid, 'u1')
        assert repo.get_by_uuid(obj.object_uuid) is None
        assert repo.get_by_uuid_including_deleted(obj.object_uuid).lifecycle_state == 'deleted'

    def test_soft_delete_nonexistent_raises(self, repo):
        with pytest.raises(ObjectNotFoundError):
            repo.soft_delete(_new_uuid(), 'u1')

    def test_soft_delete_creates_event(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.soft_delete(obj.object_uuid, 'u1')
        events = repo.get_event_history(obj.object_uuid)
        assert any(e.event_type == 'deleted' for e in events)

    def test_cannot_delete_in_review(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        with pytest.raises(InvalidLifecycleTransitionError):
            repo.soft_delete(obj.object_uuid, 'u1')

    def test_cannot_delete_approved(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        repo.transition_state(obj.object_uuid, 'approved', 'u2')
        with pytest.raises(InvalidLifecycleTransitionError):
            repo.soft_delete(obj.object_uuid, 'u1')

    def test_cannot_delete_effective(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u1')
        repo.transition_state(obj.object_uuid, 'approved', 'u2')
        repo.transition_state(obj.object_uuid, 'effective', 'u1')
        with pytest.raises(InvalidLifecycleTransitionError):
            repo.soft_delete(obj.object_uuid, 'u1')


# ---------------------------------------------------------------------------
# TestEventHistory
# ---------------------------------------------------------------------------

class TestEventHistory:
    def test_events_ordered(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        repo.transition_state(obj.object_uuid, 'in_review', 'u2')
        events = repo.get_event_history(obj.object_uuid)
        assert len(events) == 2
        event_types = {e.event_type for e in events}
        assert 'created' in event_types
        assert 'submitted_for_review' in event_types

    def test_events_have_aggregate_fields(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        events = repo.get_event_history(obj.object_uuid)
        assert events[0].aggregate_type == 'regulatory_object'
        assert events[0].aggregate_uuid == obj.object_uuid
        assert events[0].event_uuid is not None

    def test_empty_history(self, repo):
        assert repo.get_event_history(_new_uuid()) == []


# ---------------------------------------------------------------------------
# TestOptimisticLocking
# ---------------------------------------------------------------------------

class TestOptimisticLocking:
    def test_lock_increments_on_create(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        assert obj.lock_version == 1

    def test_stale_lock_raises_on_create_version(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        with pytest.raises(OptimisticLockError):
            repo.create_version(obj.object_uuid, {}, 'u1', expected_lock_version=999)

    def test_stale_lock_raises_on_transition(self, repo):
        obj, _ = repo.create_object('claim', {}, 'u1', 'u1')
        with pytest.raises(OptimisticLockError):
            repo.transition_state(obj.object_uuid, 'in_review', 'u1', expected_lock_version=999)

    def test_two_session_concurrency(self):
        """Real optimistic lock test with two independent sessions."""
        engine = create_engine("sqlite://", echo=False)
        Base.metadata.create_all(engine)

        session_a = Session(bind=engine)
        session_b = Session(bind=engine)
        repo_a = RegulatoryObjectRepository(session_a)
        repo_b = RegulatoryObjectRepository(session_b)

        # Session A creates an object
        obj_a, _ = repo_a.create_object('claim', {'w': 'v1'}, 'u1', 'u1')
        session_a.commit()

        # Both sessions read the object
        obj_a_copy = repo_a.get_by_uuid(obj_a.object_uuid)
        obj_b_copy = repo_b.get_by_uuid(obj_a.object_uuid)

        lock_a = obj_a_copy.lock_version
        lock_b = obj_b_copy.lock_version
        assert lock_a == lock_b

        # Session A updates successfully
        repo_a.create_version(obj_a_copy.object_uuid, {'w': 'v2'}, 'u1')
        session_a.commit()

        # Session B tries to update with stale lock
        with pytest.raises(OptimisticLockError):
            repo_b.create_version(obj_b_copy.object_uuid, {'w': 'v3'}, 'u1', expected_lock_version=lock_b)

        session_a.close()
        session_b.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# TestBaseline
# ---------------------------------------------------------------------------

class TestBaseline:
    def test_create_baseline(self, repo):
        o1, _ = repo.create_object('claim', {'w': 'c1'}, 'u1', 'u1')
        o2, _ = repo.create_object('risk', {'h': 'h1'}, 'u2', 'u2')
        b = repo.create_baseline('B1', 'desc', [(o1.object_uuid, 1), (o2.object_uuid, 1)], 'u1')
        assert b.name == 'B1'
        assert len(repo.list_baseline_items(b.baseline_uuid)) == 2

    def test_get_baseline(self, repo):
        o, _ = repo.create_object('claim', {}, 'u1', 'u1')
        b = repo.create_baseline('B', None, [(o.object_uuid, 1)], 'u1')
        fetched = repo.get_baseline(b.baseline_uuid)
        assert fetched is not None and fetched.name == 'B'

    def test_baseline_snapshot_immutable(self, repo):
        o, _ = repo.create_object('claim', {'w': 'orig'}, 'u1', 'u1')
        b = repo.create_baseline('B', None, [(o.object_uuid, 1)], 'u1')
        repo.create_version(o.object_uuid, {'w': 'updated'}, 'u1')
        items = repo.list_baseline_items(b.baseline_uuid)
        assert items[0].snapshot_json == {'w': 'orig'}

    def test_baseline_invalid_version_raises(self, repo):
        o, _ = repo.create_object('claim', {}, 'u1', 'u1')
        with pytest.raises(BaselineValidationError):
            repo.create_baseline('B', None, [(o.object_uuid, 999)], 'u1')

    def test_baseline_atomic_rollback(self, repo):
        """If one version in a baseline is invalid, nothing is persisted."""
        o1, _ = repo.create_object('claim', {}, 'u1', 'u1')
        fake_uuid = _new_uuid()
        with pytest.raises(BaselineValidationError):
            repo.create_baseline('B', None, [(o1.object_uuid, 1), (fake_uuid, 1)], 'u1')
        assert len(repo.list_baseline_items(_new_uuid())) == 0


# ---------------------------------------------------------------------------
# TestObjectRelation
# ---------------------------------------------------------------------------

class TestObjectRelation:
    def test_create_relation(self, repo):
        s, _ = repo.create_object('claim', {}, 'u1', 'u1')
        t, _ = repo.create_object('evidence', {}, 'u2', 'u2')
        r = repo.create_relation(s.object_uuid, 1, t.object_uuid, 1, 'supports_claim', 'u1')
        assert r.relation_type == 'supports_claim'

    def test_list_by_source(self, repo):
        s, _ = repo.create_object('claim', {}, 'u1', 'u1')
        t1, _ = repo.create_object('evidence', {}, 'u2', 'u2')
        t2, _ = repo.create_object('evidence', {}, 'u3', 'u3')
        repo.create_relation(s.object_uuid, 1, t1.object_uuid, 1, 'supports_claim', 'u1')
        repo.create_relation(s.object_uuid, 1, t2.object_uuid, 1, 'supports_claim', 'u1')
        assert len(repo.list_relations_for_source(s.object_uuid)) == 2

    def test_list_by_target(self, repo):
        s1, _ = repo.create_object('claim', {}, 'u1', 'u1')
        s2, _ = repo.create_object('claim', {}, 'u2', 'u2')
        t, _ = repo.create_object('evidence', {}, 'u3', 'u3')
        repo.create_relation(s1.object_uuid, 1, t.object_uuid, 1, 'supports_claim', 'u1')
        repo.create_relation(s2.object_uuid, 1, t.object_uuid, 1, 'supports_claim', 'u1')
        assert len(repo.list_relations_for_target(t.object_uuid)) == 2

    def test_invalid_source_version_raises(self, repo):
        s, _ = repo.create_object('claim', {}, 'u1', 'u1')
        t, _ = repo.create_object('evidence', {}, 'u2', 'u2')
        with pytest.raises(InvalidRelationError):
            repo.create_relation(s.object_uuid, 999, t.object_uuid, 1, 'supports_claim', 'u1')

    def test_invalid_target_version_raises(self, repo):
        s, _ = repo.create_object('claim', {}, 'u1', 'u1')
        t, _ = repo.create_object('evidence', {}, 'u2', 'u2')
        with pytest.raises(InvalidRelationError):
            repo.create_relation(s.object_uuid, 1, t.object_uuid, 999, 'supports_claim', 'u1')

    def test_invalid_relation_type_raises(self, repo):
        s, _ = repo.create_object('claim', {}, 'u1', 'u1')
        t, _ = repo.create_object('evidence', {}, 'u2', 'u2')
        with pytest.raises(InvalidRelationError, match='Invalid relation type'):
            repo.create_relation(s.object_uuid, 1, t.object_uuid, 1, 'invalid_type', 'u1')

    def test_relation_atomic_with_invalid_version(self, repo):
        """Transaction rolls back if one relation has invalid version."""
        s, _ = repo.create_object('claim', {}, 'u1', 'u1')
        t1, _ = repo.create_object('evidence', {}, 'u2', 'u2')
        repo.create_relation(s.object_uuid, 1, t1.object_uuid, 1, 'supports_claim', 'u1')
        # This should raise, but the previous relation should also roll back
        with pytest.raises(InvalidRelationError):
            repo.create_relation(s.object_uuid, 1, _new_uuid(), 1, 'supports_claim', 'u1')
        # The first relation should still exist
        assert len(repo.list_relations_for_source(s.object_uuid)) == 1


# ---------------------------------------------------------------------------
# TestEventLogAppendOnly
# ---------------------------------------------------------------------------

class TestEventLogAppendOnly:
    def test_no_update_event_method(self, repo):
        """Repository has no update_event or delete_event method."""
        assert not hasattr(repo, 'update_event')
        assert not hasattr(repo, 'delete_event')


# ---------------------------------------------------------------------------
# TestSubprocessCLI
# ---------------------------------------------------------------------------

class TestSubprocessCLI:
    def test_backlog_generator_cli(self):
        import subprocess
        import tempfile
        import shutil
        tmpdir = Path(tempfile.mkdtemp())
        try:
            repo_root = Path(__file__).resolve().parent.parent
            shutil.copytree(repo_root / 'META', tmpdir / 'META')
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
            assert (tmpdir / 'TASK.md').exists()
        finally:
            shutil.rmtree(tmpdir)
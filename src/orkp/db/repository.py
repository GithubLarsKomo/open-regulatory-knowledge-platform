"""Repository (data access) layer for regulatory objects."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, update, and_, exists
from sqlalchemy.orm import Session

from orkp.db.models import (
    RegulatoryObject,
    ObjectVersion,
    ObjectRelation,
    EventLog,
    ApprovalRecord,
    Baseline,
    BaselineItem,
    _new_uuid,
    _bin_to_str,
)
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    InvalidLifecycleTransitionError,
    ImmutableVersionError,
    OptimisticLockError,
    InvalidRelationError,
    BaselineValidationError,
)


# Valid lifecycle transitions per SPEC-CoreObjectStore
_VALID_TRANSITIONS: Dict[str, List[str]] = {
    'draft': ['in_review'],
    'in_review': ['approved', 'rejected'],
    'rejected': ['draft'],
    'approved': ['effective'],
    'effective': ['obsolete'],
    'obsolete': ['deleted'],
    'deleted': [],
}

# Allowed deletion transitions (admin may bypass lifecycle)
_ALLOWED_DELETION_STATES = {'draft', 'rejected', 'obsolete'}


class RegulatoryObjectRepository:
    """Data access for regulatory objects and versions."""

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_object(
        self,
        object_type: str,
        payload: Dict[str, Any],
        owner_user_id: str,
        created_by: str,
    ) -> Tuple[RegulatoryObject, ObjectVersion]:
        """Create a new regulatory object with its initial version (atomic)."""
        obj = RegulatoryObject(
            object_type=object_type,
            lifecycle_state='draft',
            owner_user_id=owner_user_id,
        )
        self.session.add(obj)
        self.session.flush()

        version = ObjectVersion(
            object_uuid=obj.object_uuid,
            version_no=1,
            payload_json=payload,
            status='draft',
            created_by=created_by,
        )
        self.session.add(version)

        self._log_event(
            aggregate_type='regulatory_object',
            aggregate_uuid=obj.object_uuid,
            event_type='created',
            event_data={'version': 1, 'payload': payload},
            actor_user_id=created_by,
        )

        return obj, version

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_uuid(self, object_uuid: bytes) -> Optional[RegulatoryObject]:
        """Get a regulatory object by UUID (excluding soft-deleted)."""
        stmt = select(RegulatoryObject).where(
            and_(
                RegulatoryObject.object_uuid == object_uuid,
                RegulatoryObject.lifecycle_state != 'deleted',
            )
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_uuid_hex(self, uuid_hex: str) -> Optional[RegulatoryObject]:
        """Get a regulatory object by hex UUID string."""
        try:
            raw_uuid = uuid.UUID(hex=uuid_hex).bytes
        except (ValueError, AttributeError):
            return None
        return self.get_by_uuid(raw_uuid)

    def get_by_uuid_including_deleted(
        self, object_uuid: bytes
    ) -> Optional[RegulatoryObject]:
        """Get a regulatory object by UUID including soft-deleted."""
        stmt = select(RegulatoryObject).where(
            RegulatoryObject.object_uuid == object_uuid,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_version(
        self, object_uuid: bytes, version_no: int
    ) -> Optional[ObjectVersion]:
        """Get a specific version of an object."""
        stmt = select(ObjectVersion).where(
            and_(
                ObjectVersion.object_uuid == object_uuid,
                ObjectVersion.version_no == version_no,
            )
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list_versions(self, object_uuid: bytes) -> List[ObjectVersion]:
        """Get all versions of an object, newest first."""
        stmt = (
            select(ObjectVersion)
            .where(ObjectVersion.object_uuid == object_uuid)
            .order_by(ObjectVersion.version_no.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_objects(
        self,
        object_type: Optional[str] = None,
        lifecycle_state: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RegulatoryObject]:
        """List regulatory objects with optional filters. Excludes deleted."""
        conditions = [RegulatoryObject.lifecycle_state != 'deleted']
        if object_type:
            conditions.append(RegulatoryObject.object_type == object_type)
        if lifecycle_state:
            conditions.append(RegulatoryObject.lifecycle_state == lifecycle_state)

        stmt = (
            select(RegulatoryObject)
            .where(and_(*conditions))
            .order_by(RegulatoryObject.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.execute(stmt).scalars().all())

    # ------------------------------------------------------------------
    # Update (with optimistic locking)
    # ------------------------------------------------------------------

    def _increment_lock(
        self, obj: RegulatoryObject, expected_version: Optional[int] = None
    ) -> bool:
        """Increment lock_version using optimistic locking.

        Returns True if the lock was acquired, False on stale version.
        """
        old = expected_version if expected_version is not None else obj.lock_version
        stmt = (
            update(RegulatoryObject)
            .where(
                and_(
                    RegulatoryObject.object_uuid == obj.object_uuid,
                    RegulatoryObject.lock_version == old,
                )
            )
            .values(
                lock_version=old + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )
        result = self.session.execute(stmt)
        if result.rowcount == 0:
            return False
        obj.lock_version = old + 1
        return True

    def _get_mutable_or_raise(self, object_uuid: bytes) -> RegulatoryObject:
        """Get object or raise ObjectNotFoundError. Also check not immutable."""
        obj = self.get_by_uuid(object_uuid)
        if obj is None:
            raise ObjectNotFoundError(f"Object {_bin_to_str(object_uuid)} not found")
        return obj

    def _check_immutable(self, obj: RegulatoryObject) -> None:
        """Raise if the object is in an immutable state."""
        if obj.lifecycle_state == 'approved':
            raise ImmutableVersionError(
                f"Object {_bin_to_str(obj.object_uuid)} is approved and cannot be modified"
            )

    def _check_not_deleted(self, obj: RegulatoryObject) -> None:
        if obj.lifecycle_state == 'deleted':
            raise ObjectNotFoundError(f"Object {_bin_to_str(obj.object_uuid)} is deleted")

    def _log_event(
        self,
        aggregate_type: str,
        aggregate_uuid: bytes,
        event_type: str,
        event_data: Optional[Dict[str, Any]] = None,
        actor_user_id: str = 'system',
    ) -> EventLog:
        """Create an append-only event log entry."""
        event = EventLog(
            aggregate_type=aggregate_type,
            aggregate_uuid=aggregate_uuid,
            event_type=event_type,
            event_data=event_data,
            actor_user_id=actor_user_id,
        )
        self.session.add(event)
        return event

    def create_version(
        self,
        object_uuid: bytes,
        payload: Dict[str, Any],
        created_by: str,
        expected_lock_version: Optional[int] = None,
    ) -> ObjectVersion:
        """Create a new version (atomic: version + lock increment + event).

        Raises:
            ObjectNotFoundError: object not found
            ImmutableVersionError: object is approved
            OptimisticLockError: stale lock version
        """
        obj = self._get_mutable_or_raise(object_uuid)
        self._check_immutable(obj)

        if not self._increment_lock(obj, expected_lock_version):
            raise OptimisticLockError(
                f"Stale lock version for object {_bin_to_str(object_uuid)}"
            )

        new_version_no = obj.current_version + 1
        version = ObjectVersion(
            object_uuid=object_uuid,
            version_no=new_version_no,
            payload_json=payload,
            status='draft',
            created_by=created_by,
        )
        self.session.add(version)

        obj.current_version = new_version_no

        self._log_event(
            aggregate_type='regulatory_object',
            aggregate_uuid=object_uuid,
            event_type='updated',
            event_data={'version': new_version_no},
            actor_user_id=created_by,
        )

        return version

    def transition_state(
        self,
        object_uuid: bytes,
        new_state: str,
        actor_user_id: str,
        comments: Optional[str] = None,
        expected_lock_version: Optional[int] = None,
    ) -> None:
        """Transition an object to a new lifecycle state (atomic).

        Raises:
            ObjectNotFoundError: object not found
            InvalidLifecycleTransitionError: transition not allowed
            OptimisticLockError: stale lock version
        """
        obj = self._get_mutable_or_raise(object_uuid)

        current = obj.lifecycle_state
        allowed = _VALID_TRANSITIONS.get(current, [])
        if new_state not in allowed:
            raise InvalidLifecycleTransitionError(
                f"Cannot transition from '{current}' to '{new_state}'"
            )

        if not self._increment_lock(obj, expected_lock_version):
            raise OptimisticLockError(
                f"Stale lock version for object {_bin_to_str(object_uuid)}"
            )

        obj.lifecycle_state = new_state

        # If approved, mark the current version as immutable
        if new_state == 'approved':
            version = self.get_version(object_uuid, obj.current_version)
            if version:
                version.status = 'approved'

        # Determine event type
        event_type = new_state
        if new_state == 'in_review':
            event_type = 'submitted_for_review'

        self._log_event(
            aggregate_type='regulatory_object',
            aggregate_uuid=object_uuid,
            event_type=event_type,
            event_data={
                'from_state': current,
                'to_state': new_state,
                'comments': comments,
            },
            actor_user_id=actor_user_id,
        )

        # Record approval decision
        if new_state in ('approved', 'rejected'):
            approval = ApprovalRecord(
                object_uuid=object_uuid,
                version_no=obj.current_version,
                decision=new_state,
                approver_user_id=actor_user_id,
                comments=comments,
            )
            self.session.add(approval)

    # ------------------------------------------------------------------
    # Soft delete — uses lifecycle policy
    # ------------------------------------------------------------------

    def soft_delete(
        self,
        object_uuid: bytes,
        actor_user_id: str,
        expected_lock_version: Optional[int] = None,
    ) -> None:
        """Soft-delete a regulatory object via lifecycle state.

        Allowed from: draft, rejected, obsolete (per _ALLOWED_DELETION_STATES).
        Not allowed from: in_review, approved, effective.

        Raises:
            ObjectNotFoundError: object not found
            InvalidLifecycleTransitionError: deletion not allowed from current state
            OptimisticLockError: stale lock version
        """
        obj = self._get_mutable_or_raise(object_uuid)

        if obj.lifecycle_state not in _ALLOWED_DELETION_STATES:
            raise InvalidLifecycleTransitionError(
                f"Cannot delete object in state '{obj.lifecycle_state}'. "
                f"Allowed from: {', '.join(sorted(_ALLOWED_DELETION_STATES))}"
            )

        if not self._increment_lock(obj, expected_lock_version):
            raise OptimisticLockError(
                f"Stale lock version for object {_bin_to_str(object_uuid)}"
            )

        obj.lifecycle_state = 'deleted'
        obj.deleted_at = datetime.now(timezone.utc)

        self._log_event(
            aggregate_type='regulatory_object',
            aggregate_uuid=object_uuid,
            event_type='deleted',
            actor_user_id=actor_user_id,
        )

    # ------------------------------------------------------------------
    # Event log
    # ------------------------------------------------------------------

    def get_event_history(
        self,
        aggregate_uuid: bytes,
        limit: int = 100,
    ) -> List[EventLog]:
        """Get the event history for an aggregate."""
        stmt = (
            select(EventLog)
            .where(EventLog.aggregate_uuid == aggregate_uuid)
            .order_by(EventLog.event_timestamp.asc(), EventLog.event_uuid.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    # ------------------------------------------------------------------
    # Object Relations (DB-OBJ-0005)
    # ------------------------------------------------------------------

    def create_relation(
        self,
        source_uuid: bytes,
        source_version: int,
        target_uuid: bytes,
        target_version: int,
        relation_type: str,
        created_by: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> ObjectRelation:
        """Create a versioned relationship between two objects.

        Validates that both source and target versions exist.
        Validates relation_type against the canonical list.

        Raises:
            InvalidRelationError: version not found or invalid relation type
        """
        sv = self.get_version(source_uuid, source_version)
        tv = self.get_version(target_uuid, target_version)
        if sv is None:
            raise InvalidRelationError(
                f"Source version {source_version} of {_bin_to_str(source_uuid)} not found"
            )
        if tv is None:
            raise InvalidRelationError(
                f"Target version {target_version} of {_bin_to_str(target_uuid)} not found"
            )

        from orkp.db.models import RELATION_TYPES
        if relation_type not in RELATION_TYPES:
            raise InvalidRelationError(
                f"Invalid relation type '{relation_type}'. Valid: {', '.join(RELATION_TYPES)}"
            )

        relation = ObjectRelation(
            source_uuid=source_uuid,
            source_version=source_version,
            target_uuid=target_uuid,
            target_version=target_version,
            relation_type=relation_type,
            properties=properties,
            created_by=created_by,
        )
        self.session.add(relation)
        return relation

    def list_relations_for_source(
        self, source_uuid: bytes
    ) -> List[ObjectRelation]:
        """List all relations where the given object is the source."""
        stmt = (
            select(ObjectRelation)
            .where(ObjectRelation.source_uuid == source_uuid)
            .order_by(ObjectRelation.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_relations_for_target(
        self, target_uuid: bytes
    ) -> List[ObjectRelation]:
        """List all relations where the given object is the target."""
        stmt = (
            select(ObjectRelation)
            .where(ObjectRelation.target_uuid == target_uuid)
            .order_by(ObjectRelation.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    # ------------------------------------------------------------------
    # Baselines (DB-OBJ-0009) — atomic with validation
    # ------------------------------------------------------------------

    def create_baseline(
        self,
        name: str,
        description: Optional[str],
        object_versions: List[Tuple[bytes, int]],
        created_by: str,
    ) -> Baseline:
        """Create a baseline with object-version pairs (atomic).

        Raises:
            BaselineValidationError: if a referenced version does not exist
        """
        baseline = Baseline(
            name=name,
            description=description,
            created_by=created_by,
        )
        self.session.add(baseline)
        self.session.flush()

        for obj_uuid, ver_no in object_versions:
            version = self.get_version(obj_uuid, ver_no)
            if version is None:
                raise BaselineValidationError(
                    f"Version {ver_no} of object {_bin_to_str(obj_uuid)} does not exist"
                )
            obj = self.get_by_uuid_including_deleted(obj_uuid)
            item = BaselineItem(
                baseline_uuid=baseline.baseline_uuid,
                object_uuid=obj_uuid,
                object_type=obj.object_type if obj else 'unknown',
                version_no=ver_no,
                snapshot_json=version.payload_json,
            )
            self.session.add(item)

        self._log_event(
            aggregate_type='baseline',
            aggregate_uuid=baseline.baseline_uuid,
            event_type='baseline_frozen',
            event_data={'name': name, 'item_count': len(object_versions)},
            actor_user_id=created_by,
        )

        return baseline

    def get_baseline(self, baseline_uuid: bytes) -> Optional[Baseline]:
        """Get a baseline by UUID."""
        stmt = select(Baseline).where(Baseline.baseline_uuid == baseline_uuid)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_baseline_items(self, baseline_uuid: bytes) -> List[BaselineItem]:
        """List all items in a baseline."""
        stmt = (
            select(BaselineItem)
            .where(BaselineItem.baseline_uuid == baseline_uuid)
            .order_by(BaselineItem.item_uuid)
        )
        return list(self.session.execute(stmt).scalars().all())
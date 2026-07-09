"""Repository (data access) layer for regulatory objects."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, update, delete, and_
from sqlalchemy.orm import Session

from orkp.db.models import (
    RegulatoryObject,
    ObjectVersion,
    EventLog,
    ApprovalRecord,
    Baseline,
    BaselineItem,
    LIFECYCLE_STATES,
    _new_uuid,
    _bin_to_str,
)


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
        """
        Create a new regulatory object with its initial version.

        Returns (regulatory_object, object_version).
        """
        obj = RegulatoryObject(
            object_type=object_type,
            lifecycle_state='draft',
            owner_user_id=owner_user_id,
        )
        self.session.add(obj)
        self.session.flush()  # get the generated UUID

        version = ObjectVersion(
            object_uuid=obj.object_uuid,
            version_no=1,
            payload_json=payload,
            status='draft',
            created_by=created_by,
        )
        self.session.add(version)

        # Log the creation event
        event = EventLog(
            object_uuid=obj.object_uuid,
            object_type=object_type,
            event_type='created',
            event_data={'version': 1, 'payload': payload},
            actor_user_id=created_by,
        )
        self.session.add(event)

        return obj, version

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_uuid(self, object_uuid: bytes) -> Optional[RegulatoryObject]:
        """Get a regulatory object by UUID (excluding soft-deleted)."""
        stmt = select(RegulatoryObject).where(
            and_(
                RegulatoryObject.object_uuid == object_uuid,
                RegulatoryObject.deleted_at.is_(None),
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
        """List regulatory objects with optional filters."""
        conditions = [RegulatoryObject.deleted_at.is_(None)]
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

    def search_objects(
        self, query: str, limit: int = 100
    ) -> List[RegulatoryObject]:
        """
        Basic search across object types and payload content.
        Uses a simple LIKE filter on object_type (extend with full-text search later).
        """
        stmt = (
            select(RegulatoryObject)
            .where(
                and_(
                    RegulatoryObject.object_type.ilike(f'%{query}%'),
                    RegulatoryObject.deleted_at.is_(None),
                )
            )
            .order_by(RegulatoryObject.updated_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def create_version(
        self,
        object_uuid: bytes,
        payload: Dict[str, Any],
        created_by: str,
    ) -> Optional[ObjectVersion]:
        """
        Create a new version of an existing draft/in_review object.

        Returns None if the object is not in a mutable state or not found.
        """
        obj = self.get_by_uuid(object_uuid)
        if obj is None:
            return None
        if obj.lifecycle_state not in ('draft', 'in_review'):
            return None  # Immutable after approval

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
        obj.updated_at = datetime.now(timezone.utc)

        event = EventLog(
            object_uuid=object_uuid,
            object_type=obj.object_type,
            event_type='updated',
            event_data={'version': new_version_no},
            actor_user_id=created_by,
        )
        self.session.add(event)

        return version

    def transition_state(
        self,
        object_uuid: bytes,
        new_state: str,
        actor_user_id: str,
        comments: Optional[str] = None,
    ) -> bool:
        """
        Transition an object to a new lifecycle state.

        Returns True if the transition succeeded, False otherwise.
        """
        obj = self.get_by_uuid(object_uuid)
        if obj is None:
            return False

        valid_transitions = {
            'draft': ['in_review'],
            'in_review': ['approved', 'rejected', 'returned_to_draft'],
            'approved': ['effective', 'obsolete'],
            'effective': ['obsolete'],
            'obsolete': [],
        }

        current = obj.lifecycle_state
        allowed = valid_transitions.get(current, [])

        if new_state not in allowed:
            return False

        obj.lifecycle_state = new_state
        obj.updated_at = datetime.now(timezone.utc)

        # If approved, mark the current version as immutable
        if new_state == 'approved':
            version = self.get_version(object_uuid, obj.current_version)
            if version:
                version.status = 'approved'

        # Log the event
        if new_state in ('approved', 'rejected', 'returned_to_draft'):
            event_type = new_state  # approved, rejected, returned_to_draft
        elif new_state == 'in_review':
            event_type = 'submitted_for_review'
        else:
            event_type = new_state

        event = EventLog(
            object_uuid=object_uuid,
            object_type=obj.object_type,
            event_type=event_type,
            event_data={
                'from_state': current,
                'to_state': new_state,
                'comments': comments,
            },
            actor_user_id=actor_user_id,
        )
        self.session.add(event)

        # Record approval decision
        if new_state in ('approved', 'rejected', 'returned_to_draft'):
            approval = ApprovalRecord(
                object_uuid=object_uuid,
                version_no=obj.current_version,
                decision=new_state,
                approver_user_id=actor_user_id,
                comments=comments,
            )
            self.session.add(approval)

        return True

    # ------------------------------------------------------------------
    # Delete (soft)
    # ------------------------------------------------------------------

    def soft_delete(self, object_uuid: bytes, actor_user_id: str) -> bool:
        """Soft-delete a regulatory object."""
        obj = self.get_by_uuid(object_uuid)
        if obj is None:
            return False

        obj.deleted_at = datetime.now(timezone.utc)
        obj.updated_at = datetime.now(timezone.utc)

        event = EventLog(
            object_uuid=object_uuid,
            object_type=obj.object_type,
            event_type='obsoleted',
            actor_user_id=actor_user_id,
        )
        self.session.add(event)
        return True

    # ------------------------------------------------------------------
    # Event log
    # ------------------------------------------------------------------

    def get_event_history(
        self,
        object_uuid: bytes,
        limit: int = 100,
    ) -> List[EventLog]:
        """Get the event history for an object."""
        stmt = (
            select(EventLog)
            .where(EventLog.object_uuid == object_uuid)
            .order_by(EventLog.event_id.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

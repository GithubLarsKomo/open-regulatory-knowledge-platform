"""Specialized read-only queries for Object Store projections."""

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from orkp.db.models import ObjectVersion, RegulatoryObject


def list_current_object_versions(
    session: Session,
    *,
    limit: int = 100,
) -> list[tuple[RegulatoryObject, ObjectVersion]]:
    """Load non-deleted objects together with their exact current versions.

    Ordering and limit semantics intentionally match
    ``RegulatoryObjectRepository.list_objects`` so callers can replace a
    list-then-get-version N+1 pattern without changing the scanned candidate set.
    """
    stmt = (
        select(RegulatoryObject, ObjectVersion)
        .join(
            ObjectVersion,
            and_(
                ObjectVersion.object_uuid == RegulatoryObject.object_uuid,
                ObjectVersion.version_no == RegulatoryObject.current_version,
            ),
        )
        .where(RegulatoryObject.lifecycle_state != "deleted")
        .order_by(RegulatoryObject.updated_at.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).all())

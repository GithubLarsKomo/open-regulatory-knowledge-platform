"""Specialized read-only queries for Object Store projections."""

from collections.abc import Iterable

from sqlalchemy import and_, select, tuple_
from sqlalchemy.orm import Session

from orkp.db.models import ObjectVersion, RegulatoryObject


VersionKey = tuple[bytes, int]
ValidationContext = tuple[RegulatoryObject, dict[int, ObjectVersion]]


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


def get_object_version_validation_contexts(
    session: Session,
    object_versions: Iterable[VersionKey],
) -> dict[bytes, ValidationContext]:
    """Load Object Store validation context for many exact references at once.

    The outer join intentionally keeps an existing object visible even when none
    of the requested exact versions exists. Callers can therefore preserve the
    distinction between "object not found" and "version not found" without an
    object/version query pair for every retrieval hit.
    """
    requested = list(dict.fromkeys(object_versions))
    if not requested:
        return {}

    object_uuids = list(dict.fromkeys(object_uuid for object_uuid, _ in requested))
    stmt = (
        select(RegulatoryObject, ObjectVersion)
        .outerjoin(
            ObjectVersion,
            and_(
                ObjectVersion.object_uuid == RegulatoryObject.object_uuid,
                tuple_(
                    ObjectVersion.object_uuid,
                    ObjectVersion.version_no,
                ).in_(requested),
            ),
        )
        .where(RegulatoryObject.object_uuid.in_(object_uuids))
    )

    contexts: dict[bytes, ValidationContext] = {}
    for obj, version in session.execute(stmt).all():
        context = contexts.get(obj.object_uuid)
        if context is None:
            versions: dict[int, ObjectVersion] = {}
            contexts[obj.object_uuid] = (obj, versions)
        else:
            _, versions = context
        if version is not None:
            versions[version.version_no] = version
    return contexts

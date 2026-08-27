"""Specialized read-only queries for Object Store projections."""

from collections.abc import Iterable

from sqlalchemy import String, and_, cast, func, or_, select, tuple_
from sqlalchemy.orm import Session

from orkp.db.models import ObjectVersion, RegulatoryObject


VersionKey = tuple[bytes, int]
ValidationContext = tuple[RegulatoryObject, dict[int, ObjectVersion]]
KeywordCandidate = tuple[bytes, int, str, dict]


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


def list_current_keyword_candidates(
    session: Session,
    tokens: Iterable[str],
    *,
    limit: int = 5000,
) -> list[KeywordCandidate]:
    """Prefilter keyword candidates inside the existing newest-object window.

    The outer token predicate is intentionally only a superset filter. Exact
    canonical tokenization, scoring and ranking remain caller-owned. Applying the
    predicate after the inner ``limit`` preserves the historical scan window:
    matching older rows cannot enter merely because newer non-matches were
    filtered out.
    """
    normalized_tokens = list(dict.fromkeys(token.lower() for token in tokens if token))
    if not normalized_tokens:
        return []

    window = (
        select(
            RegulatoryObject.object_uuid.label("object_uuid"),
            RegulatoryObject.current_version.label("current_version"),
            RegulatoryObject.object_type.label("object_type"),
            RegulatoryObject.updated_at.label("updated_at"),
            ObjectVersion.payload_json.label("payload_json"),
        )
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
        .subquery()
    )

    serialized_payload = func.lower(cast(window.c.payload_json, String))
    stmt = (
        select(
            window.c.object_uuid,
            window.c.current_version,
            window.c.object_type,
            window.c.payload_json,
        )
        .where(window.c.object_type != "ai_draft")
        .where(
            or_(
                *(
                    serialized_payload.contains(token, autoescape=True)
                    for token in normalized_tokens
                )
            )
        )
        .order_by(window.c.updated_at.desc())
    )
    return [
        (object_uuid, current_version, object_type, payload_json)
        for object_uuid, current_version, object_type, payload_json in session.execute(
            stmt
        ).all()
    ]


def get_object_version_validation_contexts(
    session: Session,
    object_versions: Iterable[VersionKey],
) -> dict[bytes, ValidationContext]:
    """Load non-deleted Object Store validation context for exact refs in bulk.

    The outer join intentionally keeps an existing non-deleted object visible even
    when none of the requested exact versions exists. Callers can therefore
    preserve the distinction between "object not found" and "version not found"
    without an object/version query pair for every retrieval hit. Soft-deleted
    objects remain invisible, matching ``RegulatoryObjectRepository.get_by_uuid``.
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
        .where(
            RegulatoryObject.object_uuid.in_(object_uuids),
            RegulatoryObject.lifecycle_state != "deleted",
        )
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

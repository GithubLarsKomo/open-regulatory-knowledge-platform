"""Set-oriented persistence reads for exact-version graph projection."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import and_, or_, select, tuple_
from sqlalchemy.orm import Session

from orkp.db.models import ObjectRelation, ObjectVersion, RegulatoryObject


VersionKey = Tuple[bytes, int]
VersionContext = Tuple[ObjectVersion, RegulatoryObject]


class GraphReadRepository:
    """Read-only set queries used by exact-version graph traversal."""

    def __init__(self, session: Session):
        self.session = session

    def get_object_version_context(
        self, object_uuid: bytes, version_no: int
    ) -> Tuple[Optional[RegulatoryObject], Optional[ObjectVersion]]:
        """Load one object and the requested exact version in one roundtrip."""
        stmt = (
            select(RegulatoryObject, ObjectVersion)
            .outerjoin(
                ObjectVersion,
                and_(
                    ObjectVersion.object_uuid == RegulatoryObject.object_uuid,
                    ObjectVersion.version_no == version_no,
                ),
            )
            .where(RegulatoryObject.object_uuid == object_uuid)
        )
        row = self.session.execute(stmt).one_or_none()
        if row is None:
            return None, None
        obj, version = row
        return obj, version

    def get_object_version_contexts(
        self, object_versions: Iterable[VersionKey]
    ) -> Dict[VersionKey, VersionContext]:
        """Load many exact object/version contexts in one roundtrip."""
        requested = list(dict.fromkeys(object_versions))
        if not requested:
            return {}

        stmt = (
            select(ObjectVersion, RegulatoryObject)
            .join(
                RegulatoryObject,
                RegulatoryObject.object_uuid == ObjectVersion.object_uuid,
            )
            .where(
                tuple_(ObjectVersion.object_uuid, ObjectVersion.version_no).in_(requested)
            )
        )
        return {
            (version.object_uuid, version.version_no): (version, obj)
            for version, obj in self.session.execute(stmt).all()
        }

    def list_active_relations_for_version_pairs(
        self, object_versions: Iterable[VersionKey]
    ) -> List[ObjectRelation]:
        """Load active relations touching any exact version pair in one roundtrip."""
        requested = list(dict.fromkeys(object_versions))
        if not requested:
            return []

        stmt = select(ObjectRelation).where(
            and_(
                ObjectRelation.lifecycle_state == "active",
                or_(
                    tuple_(
                        ObjectRelation.source_uuid,
                        ObjectRelation.source_version,
                    ).in_(requested),
                    tuple_(
                        ObjectRelation.target_uuid,
                        ObjectRelation.target_version,
                    ).in_(requested),
                ),
            )
        )
        return list(self.session.execute(stmt).scalars().all())

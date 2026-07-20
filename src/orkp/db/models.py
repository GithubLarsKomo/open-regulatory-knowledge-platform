"""
SQLAlchemy ORM models for the ORKP core object store.

These models implement the core tables defined in DATABASE/SPEC-MariaDB.md:
    - regulatory_object
    - object_version
    - object_relation
    - event_log
    - approval_record
    - generated_artifact
    - baseline
    - baseline_item
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, String, Integer, DateTime, Text, JSON, ForeignKey, LargeBinary,
    UniqueConstraint, Index, Enum as SAEnum, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Declarative base for all ORKP models."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BINARY16 = LargeBinary(16)


def _new_uuid() -> bytes:
    """Generate a new UUID as a 16-byte binary value."""
    return uuid.uuid4().bytes


def _bin_to_str(b: bytes) -> str:
    """Convert binary UUID to hex string."""
    return uuid.UUID(bytes=b).hex


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

LIFECYCLE_STATES = ('draft', 'in_review', 'approved', 'effective', 'rejected', 'obsolete', 'deleted')
RELATION_TYPES = (
    'supported_by',
    'contradicted_by',
    'mitigates',
    'verified_by',
    'validated_by',
    'references',
    'derived_from',
    'generated_from',
    'included_in',
    'impacts',
    'supersedes',
    'variant_of',
    'has_claim',
    'has_risk',
    'has_evidence',
    'governed_by',
    'manufactured_by',
    'approved_by',
    'marketed_in',
    'originates_from',
    'leads_to',
    'creates_situation',
    'may_cause',
    'estimated_by',
    'controlled_by',
    'control_verified_by',
    'control_implements',
    'residual_of',
    'benefit_risk_for',
    'overall_risk_for',
    'applies_to_product',
    'applies_to_device',
    'informed_by',
    'impacts_risk',
    'requires_review',
)
APPROVAL_DECISIONS = ('approved', 'rejected')
EVENT_TYPES = (
    'created',
    'updated',
    'submitted_for_review',
    'approved',
    'rejected',
    'deleted',
    'baseline_frozen',
    'artifact_generated',
)


# ---------------------------------------------------------------------------
# Core Tables
# ---------------------------------------------------------------------------

class RegulatoryObject(Base):
    """
    Main object registry (DB-CORE-0001, DB-CORE-0004).

    Every domain object (claim, risk, product, evidence, etc.) is registered
    here with a stable UUID, type, current version, lifecycle state and owner.
    """

    __tablename__ = 'regulatory_object'

    object_uuid: Mapped[bytes] = mapped_column(
        BINARY16, primary_key=True, default=_new_uuid
    )
    object_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lifecycle_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default='draft', index=True
    )
    owner_user_id: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationship
    versions = relationship(
        'ObjectVersion', back_populates='object_ref',
        order_by='ObjectVersion.version_no.desc()',
        cascade='all, delete-orphan',
    )

    def __repr__(self) -> str:
        return (
            f"<RegulatoryObject(uuid={_bin_to_str(self.object_uuid)}, "
            f"type={self.object_type}, version={self.current_version}, "
            f"state={self.lifecycle_state})>"
        )

    @property
    def uuid_hex(self) -> str:
        return _bin_to_str(self.object_uuid)


class ObjectVersion(Base):
    """
    Immutable version history for regulatory objects (DB-CORE-0002, DB-CORE-0005).

    Once an object version transitions to 'approved' status, it becomes
    immutable and cannot be modified or deleted.
    """

    __tablename__ = 'object_version'
    __table_args__ = (
        UniqueConstraint('object_uuid', 'version_no', name='uq_object_version'),
    )

    object_uuid: Mapped[bytes] = mapped_column(
        BINARY16,
        ForeignKey('regulatory_object.object_uuid', ondelete='RESTRICT'),
        primary_key=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='draft', index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    # Relationship
    object_ref = relationship('RegulatoryObject', back_populates='versions')

    def __repr__(self) -> str:
        return (
            f"<ObjectVersion(uuid={_bin_to_str(self.object_uuid)}, "
            f"version={self.version_no}, status={self.status})>"
        )


class ObjectRelation(Base):
    """
    Explicit versioned relationships between objects (DB-CORE-0003).

    Every relationship references explicit object versions where regulatory
    reproducibility is required.

    Supports lifecycle_state for auditable deactivation.
    """

    __tablename__ = 'object_relation'
    __table_args__ = (
        Index('ix_relation_source', 'source_uuid', 'source_version'),
        Index('ix_relation_target', 'target_uuid', 'target_version'),
        Index('ix_relation_active', 'source_uuid', 'lifecycle_state'),
        Index('ix_relation_target_active', 'target_uuid', 'lifecycle_state'),
        UniqueConstraint('source_uuid', 'source_version', 'target_uuid', 'target_version', 'relation_type',
                         name='uq_relation_duplicate'),
    )

    relation_uuid: Mapped[bytes] = mapped_column(
        BINARY16, primary_key=True, default=_new_uuid
    )
    source_uuid: Mapped[bytes] = mapped_column(BINARY16, nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    target_uuid: Mapped[bytes] = mapped_column(BINARY16, nullable=False)
    target_version: Mapped[int] = mapped_column(Integer, nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lifecycle_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default='active', index=True
    )
    properties: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    deactivated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deactivated_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    deactivation_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ObjectRelation({_bin_to_str(self.source_uuid)} v{self.source_version} "
            f"-{self.relation_type}-> "
            f"{_bin_to_str(self.target_uuid)} v{self.target_version} "
            f"[{self.lifecycle_state}])>"
        )


# ---------------------------------------------------------------------------
# Event Store & Audit Trail
# ---------------------------------------------------------------------------

class EventLog(Base):
    """
    Append-only event store for regulatory object lifecycle changes.

    Supports polymorphic aggregate references: regulatory_object, baseline,
    generated_artifact, or other entity types.
    Implements the event sourcing pattern (ADR-0001) for full auditability.

    No foreign key constraint on aggregate_uuid — the event log must remain
    valid for any entity type without cascading deletes.
    """

    __tablename__ = 'event_log'
    __table_args__ = (
        Index('ix_event_aggregate', 'aggregate_type', 'aggregate_uuid'),
        Index('ix_event_timestamp', 'event_timestamp'),
    )

    event_uuid: Mapped[bytes] = mapped_column(
        BINARY16, primary_key=True, default=_new_uuid
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default='regulatory_object',
        comment='Entity type: regulatory_object, baseline, artifact'
    )
    aggregate_uuid: Mapped[bytes] = mapped_column(
        BINARY16, nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment='created|updated|submitted_for_review|approved|rejected|deleted|baseline_frozen|artifact_generated'
    )
    event_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<EventLog(event={_bin_to_str(self.event_uuid)}, "
            f"agg={self.aggregate_type}/{_bin_to_str(self.aggregate_uuid)}, "
            f"type={self.event_type}, actor={self.actor_user_id})>"
        )


class ApprovalRecord(Base):
    """Approval history for lifecycle state transitions (WF-APP-0002, WF-APP-0003)."""

    __tablename__ = 'approval_record'

    approval_uuid: Mapped[bytes] = mapped_column(
        BINARY16, primary_key=True, default=_new_uuid
    )
    object_uuid: Mapped[bytes] = mapped_column(BINARY16, nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    approver_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signature_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ApprovalRecord(obj={_bin_to_str(self.object_uuid)}, "
            f"v{self.version_no}, {self.decision} by {self.approver_user_id})>"
        )


# ---------------------------------------------------------------------------
# Baseline & Report Artifacts
# ---------------------------------------------------------------------------

class Baseline(Base):
    """
    Frozen set of object versions used to generate a reproducible report (DB-CORE-0005).

    A baseline captures the exact version of every object used in a
    dossier or submission, enabling perfect reproducibility.
    """

    __tablename__ = 'baseline'

    baseline_uuid: Mapped[bytes] = mapped_column(
        BINARY16, primary_key=True, default=_new_uuid
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    frozen_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    # Relationships
    items = relationship(
        'BaselineItem', back_populates='baseline_ref',
        cascade='all, delete-orphan',
    )
    artifacts = relationship(
        'GeneratedArtifact', back_populates='baseline_ref',
    )

    def __repr__(self) -> str:
        return f"<Baseline(uuid={_bin_to_str(self.baseline_uuid)}, name={self.name})>"


class BaselineItem(Base):
    """Individual object version entry in a baseline."""

    __tablename__ = 'baseline_item'
    __table_args__ = (
        UniqueConstraint('baseline_uuid', 'object_uuid', 'version_no', name='uq_baseline_item'),
    )

    item_uuid: Mapped[bytes] = mapped_column(
        BINARY16, primary_key=True, default=_new_uuid
    )
    baseline_uuid: Mapped[bytes] = mapped_column(
        BINARY16,
        ForeignKey('baseline.baseline_uuid', ondelete='CASCADE'),
        nullable=False,
    )
    object_uuid: Mapped[bytes] = mapped_column(BINARY16, nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    baseline_ref = relationship('Baseline', back_populates='items')

    def __repr__(self) -> str:
        return (
            f"<BaselineItem(baseline={_bin_to_str(self.baseline_uuid)}, "
            f"obj={_bin_to_str(self.object_uuid)}, v{self.version_no})>"
        )


class GeneratedArtifact(Base):
    """
    Metadata about a generated report or submission artifact (REQ-CORE-0005).

    Links a generated document to the baseline that produced it.
    """

    __tablename__ = 'generated_artifact'

    artifact_uuid: Mapped[bytes] = mapped_column(
        BINARY16, primary_key=True, default=_new_uuid
    )
    baseline_uuid: Mapped[Optional[bytes]] = mapped_column(
        BINARY16,
        ForeignKey('baseline.baseline_uuid', ondelete='SET NULL'),
        nullable=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    generated_by: Mapped[str] = mapped_column(String(128), nullable=False)

    baseline_ref = relationship('Baseline', back_populates='artifacts')

    def __repr__(self) -> str:
        return (
            f"<GeneratedArtifact(uuid={_bin_to_str(self.artifact_uuid)}, "
            f"type={self.artifact_type}, format={self.format})>"
        )
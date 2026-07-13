-- ==========================================================================
-- ORKP Core Object Store — Initial Schema Migration (DDL)
--
-- Source requirements:
--   DB-CORE-0001: Every domain object stored with stable UUID
--   DB-CORE-0002: Object versions immutable after approval
--   DB-CORE-0003: Explicit version references for reproducibility
--   DB-CORE-0004: Soft deletion and lifecycle states
--   DB-CORE-0005: Metadata to reconstruct dossier baselines
--   WF-APP-0001: Lifecycle states: draft → in_review → approved → effective → obsolete
--
-- Target: MariaDB 10.6+
-- ==========================================================================

-- --------------------------------------------------------------------------
-- Core object registry
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS regulatory_object (
    object_uuid     BINARY(16)    NOT NULL COMMENT 'Stable UUID per DB-CORE-0001',
    object_type     VARCHAR(64)   NOT NULL COMMENT 'Domain type (claim, risk, product, ...)',
    current_version INT           NOT NULL DEFAULT 1 COMMENT 'Current version number',
    lock_version    INT           NOT NULL DEFAULT 1 COMMENT 'Optimistic locking per DB-OBJ-0004',
    lifecycle_state VARCHAR(32)   NOT NULL DEFAULT 'draft' COMMENT 'draft|in_review|approved|effective|rejected|obsolete|deleted',
    owner_user_id   VARCHAR(128)  NULL     COMMENT 'Responsible person identifier',
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at      DATETIME      NULL     COMMENT 'Soft deletion timestamp per DB-CORE-0004',
    PRIMARY KEY (object_uuid),
    INDEX ix_regobj_type (object_type),
    INDEX ix_regobj_state (lifecycle_state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Core regulatory object registry';


-- --------------------------------------------------------------------------
-- Immutable version history
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS object_version (
    object_uuid   BINARY(16)    NOT NULL COMMENT 'FK to regulatory_object',
    version_no    INT           NOT NULL COMMENT 'Monotonic version number',
    payload_json  JSON          NOT NULL COMMENT 'Full object payload at this version',
    status        VARCHAR(32)   NOT NULL DEFAULT 'draft' COMMENT 'draft|approved (immutable after approval)',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by    VARCHAR(128)  NOT NULL COMMENT 'User who created this version',
    PRIMARY KEY (object_uuid, version_no),
    INDEX ix_objver_status (status),
    CONSTRAINT fk_objver_object
        FOREIGN KEY (object_uuid) REFERENCES regulatory_object (object_uuid)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Immutable version history per DB-CORE-0002';


-- --------------------------------------------------------------------------
-- Versioned object relationships
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS object_relation (
    relation_uuid   BINARY(16)    NOT NULL COMMENT 'Stable UUID',
    source_uuid     BINARY(16)    NOT NULL COMMENT 'Source object UUID',
    source_version  INT           NOT NULL COMMENT 'Source object version',
    target_uuid     BINARY(16)    NOT NULL COMMENT 'Target object UUID',
    target_version  INT           NOT NULL COMMENT 'Target object version',
    relation_type   VARCHAR(64)   NOT NULL COMMENT 'supports_claim|mitigates|verified_by|...',
    properties      JSON          NULL     COMMENT 'Additional relation properties',
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by      VARCHAR(128)  NOT NULL COMMENT 'User who created this relation',
    PRIMARY KEY (relation_uuid),
    INDEX ix_rel_source (source_uuid, source_version),
    INDEX ix_rel_target (target_uuid, target_version),
    INDEX ix_rel_type (relation_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Versioned relationships per DB-CORE-0003';


-- --------------------------------------------------------------------------
-- Event store (append-only audit log)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event_log (
    event_id        INT           NOT NULL AUTO_INCREMENT,
    object_uuid     BINARY(16)    NOT NULL COMMENT 'FK to regulatory_object',
    object_type     VARCHAR(64)   NOT NULL COMMENT 'Denormalized for query performance',
    event_type      VARCHAR(64)   NOT NULL COMMENT 'created|updated|submitted|approved|rejected|...',
    event_data      JSON          NULL     COMMENT 'Event-specific payload',
    event_timestamp DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor_user_id   VARCHAR(128)  NOT NULL COMMENT 'User who triggered the event',
    PRIMARY KEY (event_id),
    INDEX ix_event_object (object_uuid, event_type),
    INDEX ix_event_timestamp (event_timestamp),
    CONSTRAINT fk_event_object
        FOREIGN KEY (object_uuid) REFERENCES regulatory_object (object_uuid)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Append-only event store (ADR-0001)';


-- --------------------------------------------------------------------------
-- Approval records
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS approval_record (
    approval_uuid       BINARY(16)    NOT NULL,
    object_uuid         BINARY(16)    NOT NULL COMMENT 'FK to regulatory_object',
    version_no          INT           NOT NULL COMMENT 'Approved/rejected version',
    decision            VARCHAR(32)   NOT NULL COMMENT 'approved|rejected',
    approver_user_id    VARCHAR(128)  NOT NULL COMMENT 'Who made the decision',
    decision_timestamp  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    comments            TEXT          NULL     COMMENT 'Reviewer comments (WF-APP-0003)',
    signature_data      TEXT          NULL     COMMENT 'Electronic signature (WF-APP-0005)',
    PRIMARY KEY (approval_uuid),
    INDEX ix_approval_object (object_uuid, version_no),
    CONSTRAINT fk_approval_object
        FOREIGN KEY (object_uuid) REFERENCES regulatory_object (object_uuid)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Approval history per WF-APP-0002';


-- --------------------------------------------------------------------------
-- Baselines (reproducible dossier version sets)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS baseline (
    baseline_uuid BINARY(16)    NOT NULL,
    name          VARCHAR(128)  NOT NULL COMMENT 'Human-readable baseline name',
    description   TEXT          NULL     COMMENT 'Baseline description',
    frozen_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When the baseline was frozen',
    created_by    VARCHAR(128)  NOT NULL COMMENT 'Who created the baseline',
    PRIMARY KEY (baseline_uuid),
    INDEX ix_baseline_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Frozen baseline for reproducible dossiers (DB-CORE-0005)';


CREATE TABLE IF NOT EXISTS baseline_item (
    item_uuid     BINARY(16)    NOT NULL,
    baseline_uuid BINARY(16)    NOT NULL COMMENT 'FK to baseline',
    object_uuid   BINARY(16)    NOT NULL COMMENT 'Object in the baseline',
    object_type   VARCHAR(64)   NOT NULL COMMENT 'Denormalized for query performance',
    version_no    INT           NOT NULL COMMENT 'Exact version included',
    snapshot_json JSON          NULL     COMMENT 'Optional payload snapshot at baseline time',
    PRIMARY KEY (item_uuid),
    UNIQUE KEY uq_baseline_item (baseline_uuid, object_uuid, version_no),
    CONSTRAINT fk_bitem_baseline
        FOREIGN KEY (baseline_uuid) REFERENCES baseline (baseline_uuid)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Individual object versions in a baseline';


-- --------------------------------------------------------------------------
-- Generated artifacts (report outputs)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS generated_artifact (
    artifact_uuid   BINARY(16)    NOT NULL,
    baseline_uuid   BINARY(16)    NULL     COMMENT 'FK to baseline (nullable for ad-hoc artifacts)',
    artifact_type   VARCHAR(64)   NOT NULL COMMENT 'PER|RiskReport|AnnexII|SSP|...',
    format          VARCHAR(16)   NOT NULL COMMENT 'DOCX|PDF|HTML|XML|JSON',
    file_path       VARCHAR(512)  NULL     COMMENT 'Storage path to the generated file',
    checksum        VARCHAR(128)  NULL     COMMENT 'SHA-256 of the generated file',
    generated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    generated_by    VARCHAR(128)  NOT NULL COMMENT 'Who triggered the generation',
    PRIMARY KEY (artifact_uuid),
    INDEX ix_artifact_baseline (baseline_uuid),
    INDEX ix_artifact_type (artifact_type),
    CONSTRAINT fk_artifact_baseline
        FOREIGN KEY (baseline_uuid) REFERENCES baseline (baseline_uuid)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Generated report metadata per REQ-CORE-0005';
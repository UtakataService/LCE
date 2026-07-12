-- LCE Knowledge Unit schema v2. MySQL 8.0 / MariaDB 10.6 compatible.
SET NAMES utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS knowledge_heads (
    logical_id BINARY(16) NOT NULL,
    tenant_id BINARY(16) NULL,
    current_revision_id BINARY(16) NULL,
    current_revision_no BIGINT UNSIGNED NOT NULL DEFAULT 0,
    status VARCHAR(32) CHARACTER SET ascii NOT NULL,
    lock_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    retracted_at DATETIME(6) NULL,
    PRIMARY KEY (logical_id),
    KEY ix_knowledge_heads_status (status, updated_at, logical_id),
    KEY ix_knowledge_heads_tenant_status (tenant_id, status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS knowledge_revisions (
    revision_id BINARY(16) NOT NULL,
    logical_id BINARY(16) NOT NULL,
    revision_no BIGINT UNSIGNED NOT NULL,
    subject_namespace VARCHAR(32) NOT NULL,
    subject_id VARCHAR(191) NOT NULL,
    relation_id VARCHAR(64) NOT NULL,
    object_kind VARCHAR(32) CHARACTER SET ascii NOT NULL,
    object_ref VARCHAR(191) NULL,
    object_text LONGTEXT NULL,
    object_number DECIMAL(38,12) NULL,
    object_json JSON NULL,
    language_tag VARCHAR(35) CHARACTER SET ascii NOT NULL DEFAULT 'und',
    scope_json JSON NOT NULL,
    confidence DECIMAL(7,6) NOT NULL,
    valid_from DATETIME(6) NULL,
    valid_to DATETIME(6) NULL,
    schema_version VARCHAR(32) CHARACTER SET ascii NOT NULL,
    content_hash BINARY(32) NOT NULL,
    created_by VARCHAR(191) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (revision_id),
    UNIQUE KEY uq_knowledge_revision_no (logical_id, revision_no),
    KEY ix_knowledge_revision_hash (logical_id, content_hash),
    KEY ix_knowledge_claim (subject_namespace, subject_id, relation_id),
    KEY ix_knowledge_object (relation_id, object_kind, object_ref),
    KEY ix_knowledge_language_time (language_tag, created_at),
    CONSTRAINT fk_revision_head FOREIGN KEY (logical_id)
      REFERENCES knowledge_heads(logical_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

ALTER TABLE knowledge_heads
  ADD CONSTRAINT fk_head_current_revision FOREIGN KEY (current_revision_id)
  REFERENCES knowledge_revisions(revision_id) ON DELETE RESTRICT;

CREATE TABLE IF NOT EXISTS evidence_sources (
    source_id BINARY(16) NOT NULL,
    source_kind VARCHAR(32) CHARACTER SET ascii NOT NULL,
    canonical_uri TEXT NULL,
    license_code VARCHAR(64) CHARACTER SET ascii NULL,
    independence_group VARCHAR(191) NULL,
    lineage_hash BINARY(32) NULL,
    fetched_at DATETIME(6) NULL,
    metadata_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (source_id),
    KEY ix_evidence_source_lineage (lineage_hash),
    KEY ix_evidence_source_independence (independence_group)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id BINARY(16) NOT NULL,
    source_id BINARY(16) NOT NULL,
    overlay_id VARCHAR(191) NULL,
    content_hash BINARY(32) NOT NULL,
    raw_text LONGTEXT NULL,
    blob_ref TEXT NULL,
    language_tag VARCHAR(35) CHARACTER SET ascii NOT NULL DEFAULT 'und',
    observed_at DATETIME(6) NULL,
    payload_json JSON NOT NULL,
    redacted_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (evidence_id),
    KEY ix_evidence_hash (content_hash),
    KEY ix_evidence_source_time (source_id, observed_at),
    KEY ix_evidence_overlay_time (overlay_id, observed_at),
    CONSTRAINT fk_evidence_source FOREIGN KEY (source_id)
      REFERENCES evidence_sources(source_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS evidence_links (
    revision_id BINARY(16) NOT NULL,
    evidence_id BINARY(16) NOT NULL,
    stance VARCHAR(32) CHARACTER SET ascii NOT NULL,
    relevance DECIMAL(7,6) NOT NULL DEFAULT 1.0,
    reliability DECIMAL(7,6) NOT NULL DEFAULT 1.0,
    scope_json JSON NOT NULL,
    interpretation TEXT NULL,
    linked_by VARCHAR(191) NOT NULL,
    linked_at DATETIME(6) NOT NULL,
    PRIMARY KEY (revision_id, evidence_id, stance),
    KEY ix_evidence_link_item (evidence_id, stance),
    CONSTRAINT fk_link_revision FOREIGN KEY (revision_id)
      REFERENCES knowledge_revisions(revision_id) ON DELETE RESTRICT,
    CONSTRAINT fk_link_evidence FOREIGN KEY (evidence_id)
      REFERENCES evidence_items(evidence_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS knowledge_events (
    event_id BINARY(16) NOT NULL,
    logical_id BINARY(16) NOT NULL,
    revision_id BINARY(16) NULL,
    from_status VARCHAR(32) CHARACTER SET ascii NULL,
    to_status VARCHAR(32) CHARACTER SET ascii NOT NULL,
    event_kind VARCHAR(32) CHARACTER SET ascii NOT NULL,
    actor_kind VARCHAR(32) CHARACTER SET ascii NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason_code VARCHAR(64) CHARACTER SET ascii NOT NULL,
    policy_version VARCHAR(32) CHARACTER SET ascii NOT NULL,
    details_json JSON NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    request_id VARCHAR(191) CHARACTER SET ascii NOT NULL,
    PRIMARY KEY (event_id),
    UNIQUE KEY uq_knowledge_event_request (request_id),
    KEY ix_knowledge_event_history (logical_id, occurred_at, event_id),
    CONSTRAINT fk_event_head FOREIGN KEY (logical_id)
      REFERENCES knowledge_heads(logical_id) ON DELETE RESTRICT,
    CONSTRAINT fk_event_revision FOREIGN KEY (revision_id)
      REFERENCES knowledge_revisions(revision_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS knowledge_outbox (
    outbox_id BINARY(16) NOT NULL,
    aggregate_id BINARY(16) NOT NULL,
    aggregate_version BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(64) CHARACTER SET ascii NOT NULL,
    payload_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL,
    available_at DATETIME(6) NOT NULL,
    claimed_at DATETIME(6) NULL,
    published_at DATETIME(6) NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    last_error TEXT NULL,
    PRIMARY KEY (outbox_id),
    UNIQUE KEY uq_outbox_aggregate_event (aggregate_id, aggregate_version, event_type),
    KEY ix_outbox_pending (published_at, available_at, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

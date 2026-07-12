-- LCE Knowledge Unit schema v3. MySQL 8.0 / MariaDB 10.6 conservative subset.
CREATE TABLE IF NOT EXISTS knowledge_heads (
 tenant_id VARCHAR(128) NOT NULL, logical_id BINARY(16) NOT NULL,
 current_revision_id BINARY(16) NULL, current_revision_no BIGINT UNSIGNED NOT NULL DEFAULT 0,
 status VARCHAR(32) NOT NULL, lock_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
 created_at DATETIME(6) NOT NULL, updated_at DATETIME(6) NOT NULL,
 PRIMARY KEY(tenant_id,logical_id), UNIQUE KEY uq_head_revision(tenant_id,current_revision_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS knowledge_revisions (
 tenant_id VARCHAR(128) NOT NULL, revision_id BINARY(16) NOT NULL, logical_id BINARY(16) NOT NULL,
 revision_no BIGINT UNSIGNED NOT NULL, status VARCHAR(32) NOT NULL,
 claim_json JSON NOT NULL, scope_json JSON NOT NULL, language_json JSON NOT NULL,
 confidence DECIMAL(7,6) NOT NULL DEFAULT 0, content_hash BINARY(32) NOT NULL,
 created_by VARCHAR(255) NOT NULL, created_at DATETIME(6) NOT NULL,
 PRIMARY KEY(tenant_id,revision_id), UNIQUE KEY uq_revision_no(tenant_id,logical_id,revision_no),
 KEY ix_revision_hash(tenant_id,content_hash),
 CONSTRAINT fk_revision_head FOREIGN KEY(tenant_id,logical_id) REFERENCES knowledge_heads(tenant_id,logical_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS evidence_items (
 tenant_id VARCHAR(128) NOT NULL, evidence_id BINARY(16) NOT NULL,
 raw_text LONGTEXT NOT NULL, normalized_text LONGTEXT NOT NULL, source_uri TEXT NOT NULL,
 content_hash BINARY(32) NOT NULL, license_code VARCHAR(128) NOT NULL, language_tag VARCHAR(64) NOT NULL,
 created_at DATETIME(6) NOT NULL, PRIMARY KEY(tenant_id,evidence_id), KEY ix_evidence_hash(tenant_id,content_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS evidence_links (
 tenant_id VARCHAR(128) NOT NULL, revision_id BINARY(16) NOT NULL, evidence_id BINARY(16) NOT NULL,
 stance VARCHAR(32) NOT NULL, source_ref VARCHAR(512) NOT NULL, linked_by VARCHAR(255) NOT NULL, linked_at DATETIME(6) NOT NULL,
 PRIMARY KEY(tenant_id,revision_id,evidence_id,stance),
 CONSTRAINT fk_link_revision FOREIGN KEY(tenant_id,revision_id) REFERENCES knowledge_revisions(tenant_id,revision_id),
 CONSTRAINT fk_link_evidence FOREIGN KEY(tenant_id,evidence_id) REFERENCES evidence_items(tenant_id,evidence_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS knowledge_events (
 tenant_id VARCHAR(128) NOT NULL, event_id BINARY(16) NOT NULL, logical_id BINARY(16) NOT NULL,
 revision_id BINARY(16) NOT NULL, from_status VARCHAR(32) NULL, to_status VARCHAR(32) NOT NULL,
 actor_id VARCHAR(255) NOT NULL, request_id VARCHAR(191) NOT NULL, occurred_at DATETIME(6) NOT NULL,
 PRIMARY KEY(tenant_id,event_id), UNIQUE KEY uq_event_request(tenant_id,request_id),
 CONSTRAINT fk_event_revision FOREIGN KEY(tenant_id,revision_id) REFERENCES knowledge_revisions(tenant_id,revision_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS idempotency_records (
 tenant_id VARCHAR(128) NOT NULL, request_id VARCHAR(191) NOT NULL, command_hash BINARY(32) NOT NULL,
 state VARCHAR(16) NOT NULL, logical_id BINARY(16) NULL, revision_id BINARY(16) NULL,
 created_at DATETIME(6) NOT NULL, completed_at DATETIME(6) NULL,
 PRIMARY KEY(tenant_id,request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS knowledge_outbox (
 tenant_id VARCHAR(128) NOT NULL, outbox_id BINARY(16) NOT NULL, aggregate_id BINARY(16) NOT NULL,
 aggregate_version BIGINT UNSIGNED NOT NULL, event_type VARCHAR(128) NOT NULL, payload_json JSON NOT NULL,
 created_at DATETIME(6) NOT NULL, available_at DATETIME(6) NOT NULL, claimed_at DATETIME(6) NULL,
 published_at DATETIME(6) NULL, attempts INT UNSIGNED NOT NULL DEFAULT 0,
 PRIMARY KEY(tenant_id,outbox_id), UNIQUE KEY uq_outbox_event(tenant_id,aggregate_id,aggregate_version,event_type),
 KEY ix_outbox_pending(tenant_id,published_at,available_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

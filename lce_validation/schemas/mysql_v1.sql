-- Run this migration after selecting the application database.
-- utf8mb4_unicode_ci keeps the schema usable on MySQL 8 and current MariaDB.

CREATE TABLE IF NOT EXISTS language_overlays (
  overlay_id VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin PRIMARY KEY,
  session_id VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  source_language VARCHAR(35) NOT NULL DEFAULT 'und',
  state VARCHAR(32) NOT NULL,
  version BIGINT UNSIGNED NOT NULL DEFAULT 0,
  payload_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  INDEX ix_overlay_session (session_id),
  INDEX ix_overlay_language_state (source_language, state),
  INDEX ix_overlay_updated (updated_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS knowledge_units (
  knowledge_id BINARY(16) PRIMARY KEY,
  version BIGINT UNSIGNED NOT NULL,
  status VARCHAR(32) NOT NULL,
  subject_id VARCHAR(191) NOT NULL,
  relation_id VARCHAR(191) NOT NULL,
  object_json JSON NOT NULL,
  language_tag VARCHAR(35) NOT NULL DEFAULT 'und',
  confidence DECIMAL(7,6) NOT NULL,
  valid_from DATETIME(6) NULL,
  valid_to DATETIME(6) NULL,
  provenance_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  UNIQUE KEY uq_knowledge_version (knowledge_id, version),
  INDEX ix_knowledge_sp (subject_id, relation_id),
  INDEX ix_knowledge_status_language (status, language_tag)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS knowledge_evidence (
  evidence_id BINARY(16) PRIMARY KEY,
  knowledge_id BINARY(16) NULL,
  overlay_id VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL,
  evidence_kind VARCHAR(64) NOT NULL,
  source_uri TEXT NULL,
  content_hash BINARY(32) NOT NULL,
  payload_json JSON NOT NULL,
  observed_at DATETIME(6) NOT NULL,
  FOREIGN KEY (overlay_id) REFERENCES language_overlays(overlay_id),
  INDEX ix_evidence_knowledge (knowledge_id),
  INDEX ix_evidence_overlay (overlay_id),
  INDEX ix_evidence_hash (content_hash)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS graph_edges (
  edge_id BINARY(16) PRIMARY KEY,
  source_id VARCHAR(191) NOT NULL,
  relation_type VARCHAR(64) NOT NULL,
  target_id VARCHAR(191) NOT NULL,
  status VARCHAR(32) NOT NULL,
  weight DECIMAL(9,8) NOT NULL,
  provenance_json JSON NOT NULL,
  version BIGINT UNSIGNED NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  INDEX ix_graph_source_relation (source_id, relation_type),
  INDEX ix_graph_target_relation (target_id, relation_type)
) ENGINE=InnoDB;

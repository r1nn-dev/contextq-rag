-- V5__create_guest_sessions_guest_usage_logs.sql
-- Guest sessions and usage logs (db-design §3.4, §3.5, policy §1.3, INV-16).
-- Only the SHA-256 hex of the devdocs_sid cookie is stored.

CREATE TABLE guest_sessions (
    id         BIGINT GENERATED ALWAYS AS IDENTITY,
    sid_hash   CHAR(64)       NOT NULL,
    ip_address VARCHAR(45)    NOT NULL,
    used_count SMALLINT       NOT NULL,
    status     VARCHAR(30)    NOT NULL,
    expires_at TIMESTAMPTZ(6) NOT NULL,   -- first question + 24 h, absolute
    created_at TIMESTAMPTZ(6) NOT NULL,
    updated_at TIMESTAMPTZ(6) NOT NULL,
    CONSTRAINT pk_guest_sessions PRIMARY KEY (id),
    CONSTRAINT uq_gs_sid_hash UNIQUE (sid_hash),
    CONSTRAINT chk_gs_used_count CHECK (used_count BETWEEN 0 AND 5)   -- INV-16
);

-- new sessions per IP per hour (GUEST_SESSION_LIMIT) and batch cleanup
CREATE INDEX idx_gs_ip_created ON guest_sessions (ip_address, created_at);
CREATE INDEX idx_gs_expires_at ON guest_sessions (expires_at);

-- [IMMUTABLE] no FK: kept for aggregation after the session row is deleted
CREATE TABLE guest_usage_logs (
    id                BIGINT GENERATED ALWAYS AS IDENTITY,
    sid_hash          CHAR(64)       NOT NULL,
    status            VARCHAR(30)    NOT NULL,
    prompt_tokens     INT            NULL,
    completion_tokens INT            NULL,
    created_at        TIMESTAMPTZ(6) NOT NULL,
    CONSTRAINT pk_guest_usage_logs PRIMARY KEY (id)
);

CREATE INDEX idx_gul_sid_hash ON guest_usage_logs (sid_hash);
CREATE INDEX idx_gul_created_at ON guest_usage_logs (created_at);

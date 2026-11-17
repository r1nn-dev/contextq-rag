-- V2__create_users_conversations_messages.sql
-- app schema: users, conversations, messages, message_sources (db-design §3.1, §3.6~§3.8)
-- Rules (db-design §4): IDENTITY PK, TIMESTAMPTZ(6), no DB DEFAULT, no ON DELETE CASCADE.
-- Cross-service references (source_key, ingest_run_id) store values only, no FK.

CREATE TABLE users (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY,
    email              VARCHAR(254)   NOT NULL,
    password_hash      VARCHAR(72)    NOT NULL,
    role               VARCHAR(30)    NOT NULL,
    status             VARCHAR(30)    NOT NULL,
    login_failed_count SMALLINT       NOT NULL,
    locked_at          TIMESTAMPTZ(6) NULL,
    created_at         TIMESTAMPTZ(6) NOT NULL,
    updated_at         TIMESTAMPTZ(6) NOT NULL,
    CONSTRAINT pk_users PRIMARY KEY (id),
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT chk_users_failed_count CHECK (login_failed_count BETWEEN 0 AND 5)
);

CREATE INDEX idx_users_status_locked ON users (status, locked_at);

CREATE TABLE conversations (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY,
    user_id             BIGINT         NOT NULL,
    title               VARCHAR(40)    NOT NULL,
    mode                VARCHAR(30)    NOT NULL,
    source_key          VARCHAR(50)    NULL,
    source_key_a        VARCHAR(50)    NULL,
    source_key_b        VARCHAR(50)    NULL,
    message_count       INT            NOT NULL,
    last_message_status VARCHAR(30)    NULL,
    created_at          TIMESTAMPTZ(6) NOT NULL,
    updated_at          TIMESTAMPTZ(6) NOT NULL,
    CONSTRAINT pk_conversations PRIMARY KEY (id),
    CONSTRAINT fk_conv_user FOREIGN KEY (user_id) REFERENCES users (id),
    -- SINGLE: source_key only / COMPARE: source_key_a and source_key_b only
    CONSTRAINT chk_conv_mode_source CHECK (
        (mode = 'SINGLE' AND source_key IS NOT NULL AND source_key_a IS NULL AND source_key_b IS NULL)
        OR
        (mode = 'COMPARE' AND source_key IS NULL AND source_key_a IS NOT NULL AND source_key_b IS NOT NULL)
    )
);

-- cursor pagination of the conversation list (20 per page)
CREATE INDEX idx_conv_user_updated ON conversations (user_id, updated_at DESC);

CREATE TABLE messages (
    id                BIGINT GENERATED ALWAYS AS IDENTITY,
    conversation_id   BIGINT         NOT NULL,
    user_id           BIGINT         NOT NULL,
    role              VARCHAR(30)    NOT NULL,
    content           TEXT           NULL,
    quota_cost        SMALLINT       NULL,
    request_id        VARCHAR(36)    NULL,
    status            VARCHAR(30)    NULL,
    status_reason     VARCHAR(50)    NULL,
    finish_reason     VARCHAR(20)    NULL,
    rewritten_query   VARCHAR(200)   NULL,
    rewrite_status    VARCHAR(20)    NULL,
    ingest_run_id     BIGINT         NULL,
    ingest_run_id_a   BIGINT         NULL,
    ingest_run_id_b   BIGINT         NULL,
    commit_sha        CHAR(40)       NULL,
    commit_sha_a      CHAR(40)       NULL,
    commit_sha_b      CHAR(40)       NULL,
    ingested_at       DATE           NULL,
    ingested_at_a     DATE           NULL,
    ingested_at_b     DATE           NULL,
    top1_similarity   DECIMAL(5, 4)  NULL,
    top1_similarity_a DECIMAL(5, 4)  NULL,
    top1_similarity_b DECIMAL(5, 4)  NULL,
    model             VARCHAR(50)    NULL,
    prompt_version    VARCHAR(50)    NULL,
    prompt_tokens     INT            NULL,
    completion_tokens INT            NULL,
    invalid_citations JSONB          NULL,
    compare_result    JSONB          NULL,
    rewrite_ms        INT            NULL,
    embed_ms          INT            NULL,
    retrieve_ms       INT            NULL,
    ttft_ms           INT            NULL,
    total_ms          INT            NULL,
    created_at        TIMESTAMPTZ(6) NOT NULL,
    updated_at        TIMESTAMPTZ(6) NOT NULL,
    CONSTRAINT pk_messages PRIMARY KEY (id),
    CONSTRAINT fk_msg_conv FOREIGN KEY (conversation_id) REFERENCES conversations (id),
    CONSTRAINT fk_msg_user FOREIGN KEY (user_id) REFERENCES users (id)
);

-- conversation detail: messages in time order
CREATE INDEX idx_msg_conv_created ON messages (conversation_id, created_at);
-- INV-11: in-progress ASSISTANT message check
CREATE INDEX idx_msg_conv_role_status ON messages (conversation_id, role, status);
-- daily quota: SUM(quota_cost) WHERE role = 'USER' AND created_at >= today 00:00 KST
CREATE INDEX idx_msg_user_quota ON messages (user_id, role, created_at DESC);

-- [IMMUTABLE] value snapshot of sources (INV-13): created_at only
CREATE TABLE message_sources (
    id           BIGINT GENERATED ALWAYS AS IDENTITY,
    message_id   BIGINT         NOT NULL,
    source_key   VARCHAR(50)    NOT NULL,
    rank_label   VARCHAR(5)     NOT NULL,
    chunk_id     CHAR(32)       NULL,      -- not in SSE meta.sources (db-design §3.8)
    heading_path TEXT           NOT NULL,
    permalink    TEXT           NOT NULL,
    site_url     TEXT           NULL,
    similarity   DECIMAL(5, 4)  NOT NULL,
    created_at   TIMESTAMPTZ(6) NOT NULL,
    CONSTRAINT pk_message_sources PRIMARY KEY (id),
    CONSTRAINT fk_ms_message FOREIGN KEY (message_id) REFERENCES messages (id)
);

CREATE INDEX idx_ms_message_id ON message_sources (message_id);

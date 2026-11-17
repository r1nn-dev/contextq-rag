-- V4__create_token_families_refresh_tokens.sql
-- Refresh token rotation (db-design §3.2, §3.3, policy §1.2, INV-15).
-- Only the SHA-256 hex of the opaque token is stored; the raw value lives in the HttpOnly cookie.

CREATE TABLE token_families (
    id         BIGINT GENERATED ALWAYS AS IDENTITY,
    user_id    BIGINT         NOT NULL,
    status     VARCHAR(30)    NOT NULL,
    expires_at TIMESTAMPTZ(6) NOT NULL,   -- login time + 7 days, absolute (no extension)
    created_at TIMESTAMPTZ(6) NOT NULL,
    updated_at TIMESTAMPTZ(6) NOT NULL,
    CONSTRAINT pk_token_families PRIMARY KEY (id),
    CONSTRAINT fk_tf_user FOREIGN KEY (user_id) REFERENCES users (id)
);

-- ACTIVE families per user (cap 10) and batch cleanup
CREATE INDEX idx_tf_user_status ON token_families (user_id, status);
CREATE INDEX idx_tf_expires_at ON token_families (expires_at);

CREATE TABLE refresh_tokens (
    id         BIGINT GENERATED ALWAYS AS IDENTITY,
    family_id  BIGINT         NOT NULL,
    token_hash CHAR(64)       NOT NULL,
    status     VARCHAR(30)    NOT NULL,
    created_at TIMESTAMPTZ(6) NOT NULL,
    updated_at TIMESTAMPTZ(6) NOT NULL,   -- status change time: USED + 5 s = reuse grace
    CONSTRAINT pk_refresh_tokens PRIMARY KEY (id),
    CONSTRAINT uq_rt_token_hash UNIQUE (token_hash),
    CONSTRAINT fk_rt_family FOREIGN KEY (family_id) REFERENCES token_families (id)
);

CREATE INDEX idx_rt_family_status ON refresh_tokens (family_id, status);

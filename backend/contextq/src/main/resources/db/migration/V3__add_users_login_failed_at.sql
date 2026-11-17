-- V3__add_users_login_failed_at.sql
-- Start of the current login failure window (db-design §3.1, policy §1.2 "15분 내 5회").
-- A failure after login_failed_at + 15 minutes starts a new window. NULL after a success.
ALTER TABLE users ADD COLUMN login_failed_at TIMESTAMPTZ(6) NULL;

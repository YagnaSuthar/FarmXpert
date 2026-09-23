/**
 * Migration: Create refresh_tokens table
 *
 * Stores hashed refresh tokens for persistent "Remember Me" authentication.
 * Uses SHA-256 token hash (token_hash) instead of raw token.
 * References users(id) with ON DELETE CASCADE.
 */

const UP = `
  CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(64) NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked     BOOLEAN NOT NULL DEFAULT FALSE,
    user_agent  TEXT,
    ip_address  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );

  CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
  CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);
`;

const DOWN = `
  DROP TABLE IF EXISTS refresh_tokens CASCADE;
`;

module.exports = { name: '005_create_refresh_tokens_table', up: UP, down: DOWN };

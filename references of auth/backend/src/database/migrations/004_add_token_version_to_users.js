/**
 * Migration: Add token_version to users table
 *
 * Adds `token_version` (integer, default 1) to `users`.
 * Incrementing `token_version` immediately invalidates all previously
 * issued stateless JWT tokens for that user upon password reset or security revocation.
 */

const UP = `
  ALTER TABLE users
  ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 1;
`;

const DOWN = `
  ALTER TABLE users
  DROP COLUMN IF EXISTS token_version;
`;

module.exports = { name: '004_add_token_version_to_users', up: UP, down: DOWN };

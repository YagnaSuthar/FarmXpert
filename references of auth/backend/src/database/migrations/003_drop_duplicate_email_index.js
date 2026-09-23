/**
 * Migration: Drop redundant email index
 *
 * `email VARCHAR(255) UNIQUE` already creates the unique index constraint `users_email_key`.
 * `idx_users_email` is redundant and can be safely dropped.
 */

const UP = `
  DROP INDEX IF EXISTS idx_users_email;
`;

const DOWN = `
  CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
`;

module.exports = { name: '003_drop_duplicate_email_index', up: UP, down: DOWN };

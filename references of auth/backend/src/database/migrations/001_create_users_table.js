/**
 * Migration: Create users table
 *
 * Stores user accounts with role-based access control.
 * Uses UUID primary keys (gen_random_uuid) to prevent row count leakage.
 *
 * Roles: user, manager, admin, super_admin
 * Default role: user
 * email_verified defaults to false (requires OTP verification)
 */

const UP = `
  CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'user'
                    CHECK (role IN ('user', 'manager', 'admin', 'super_admin')),
    email_verified  BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );

  CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
  CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
`;

const DOWN = `
  DROP TABLE IF EXISTS users CASCADE;
`;

module.exports = { name: '001_create_users_table', up: UP, down: DOWN };

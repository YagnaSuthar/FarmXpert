/**
 * Migration: Create otp_verifications table
 *
 * Stores hashed OTPs for email verification and password reset.
 *
 * Security:
 * - OTP is stored as a SHA-256 hash (never plaintext)
 * - Expires after configurable duration
 * - Tracks verification attempts to prevent brute force
 * - Single-use flag prevents OTP reuse
 * - Foreign key cascades on user deletion
 */

const UP = `
  CREATE TABLE IF NOT EXISTS otp_verifications (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose     VARCHAR(30) NOT NULL
                CHECK (purpose IN ('email_verification', 'password_reset')),
    otp_hash    VARCHAR(255) NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    used        BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );

  CREATE INDEX IF NOT EXISTS idx_otp_user_purpose
    ON otp_verifications(user_id, purpose);

  CREATE INDEX IF NOT EXISTS idx_otp_expires
    ON otp_verifications(expires_at);
`;

const DOWN = `
  DROP TABLE IF EXISTS otp_verifications CASCADE;
`;

module.exports = { name: '002_create_otp_verifications_table', up: UP, down: DOWN };

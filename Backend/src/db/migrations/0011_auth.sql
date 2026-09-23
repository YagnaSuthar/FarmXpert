-- 0011 Accounts: email + password login, email verification, password reset,
-- rotating refresh tokens, roles, onboarding.
--
-- Ported from the reference auth design (references of auth/backend):
--   password + pepper -> bcrypt(12); pepper lives only in the environment
--   6-digit codes stored as HMAC-SHA256, 10-minute expiry, 5 attempts, single use
--   arithmetic CAPTCHA, answer stored as HMAC, 3 attempts, single use
--   15-minute access JWT carrying token_version; bumping it revokes every JWT
--   refresh tokens stored as SHA-256, rotated on every use; presenting an
--   already-rotated token revokes the whole family (theft detection)
-- One change from the reference: captchas, reset authorisations and privileged
-- sessions lived in process memory there. Here they are rows, so login keeps
-- working across several workers (WEB_CONCURRENCY) and restarts.

ALTER TABLE users
    ADD COLUMN email          varchar(255),
    ADD COLUMN password_hash  varchar(255),
    ADD COLUMN role           varchar(20) NOT NULL DEFAULT 'farmer',
    ADD COLUMN email_verified boolean     NOT NULL DEFAULT false,
    ADD COLUMN token_version  integer     NOT NULL DEFAULT 1,
    ADD COLUMN onboarded_at   timestamptz,
    ADD COLUMN last_login_at  timestamptz,
    -- Brute-force guard: a captcha after 3 misses, a 15-minute lock after 10.
    ADD COLUMN failed_logins  integer     NOT NULL DEFAULT 0,
    ADD COLUMN locked_until   timestamptz,
    ADD CONSTRAINT ck_users_role_known CHECK (role IN ('farmer', 'agronomist', 'admin', 'super_admin')),
    ADD CONSTRAINT ck_users_email_shape CHECK (email IS NULL OR email = lower(email));
-- Case-insensitive by construction (stored lower-case); a deleted account
-- releases its address.
CREATE UNIQUE INDEX uq_users_email_active ON users (email) WHERE deleted_at IS NULL AND email IS NOT NULL;

CREATE TABLE otp_verifications (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    purpose    varchar(30) NOT NULL,
    otp_hash   varchar(64) NOT NULL,
    expires_at timestamptz NOT NULL,
    attempts   integer     NOT NULL DEFAULT 0,
    used       boolean     NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_otp_purpose_known CHECK (purpose IN ('email_verification', 'password_reset'))
);
-- "The newest live code for this user and purpose."
CREATE INDEX ix_otp_user_purpose_live ON otp_verifications (user_id, purpose, created_at DESC)
    WHERE NOT used;
CREATE INDEX ix_otp_expires ON otp_verifications (expires_at);

CREATE TABLE refresh_tokens (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    -- All tokens descended from one login share a family: reuse of any
    -- rotated token revokes the family, not just the one token.
    family_id   uuid        NOT NULL,
    token_hash  varchar(64) NOT NULL UNIQUE,
    expires_at  timestamptz NOT NULL,
    revoked_at  timestamptz,
    persistent  boolean     NOT NULL DEFAULT false,
    user_agent  varchar(300),
    ip_address  varchar(64),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_refresh_tokens_user ON refresh_tokens (user_id) WHERE revoked_at IS NULL;
CREATE INDEX ix_refresh_tokens_family ON refresh_tokens (family_id);
CREATE INDEX ix_refresh_tokens_expires ON refresh_tokens (expires_at);

-- Short-lived, single-use secrets: CAPTCHA answers and password-reset
-- authorisations. UNLOGGED: no WAL, several times faster to write, and losing
-- them in a crash only means asking for a new captcha.
CREATE UNLOGGED TABLE auth_challenges (
    id          varchar(64) PRIMARY KEY,      -- SHA-256 of the id the client holds
    kind        varchar(16) NOT NULL,
    secret_hash varchar(64),
    user_id     uuid        REFERENCES users (id) ON DELETE CASCADE,
    attempts    integer     NOT NULL DEFAULT 0,
    expires_at  timestamptz NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_auth_challenges_kind_known CHECK (kind IN ('captcha', 'password_reset'))
);
CREATE INDEX ix_auth_challenges_expires ON auth_challenges (expires_at);

-- What the agents use beyond the soil and the crop: labour, water, equipment,
-- budget and working hours (the task scheduler plans within them) and whether
-- irrigation is possible at all (crop choice).
ALTER TABLE farms
    ADD COLUMN resources jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN water_source varchar(40);

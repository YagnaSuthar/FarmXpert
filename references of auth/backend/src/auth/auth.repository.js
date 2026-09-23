const { pool } = require('../config/db');

/**
 * Auth Repository
 *
 * Responsible for PostgreSQL queries related to
 * authentication, users, and OTP records.
 *
 * RULES:
 * - All queries use parameterized statements ($1, $2, etc.)
 * - No SQL string concatenation
 * - No HTTP response logic
 * - Returns raw data objects (rows)
 */

const authRepository = {
  // ─── User Queries ─────────────────────────────────────

  /**
   * Find a user by email.
   * @param {string} email
   * @returns {Promise<Object|null>}
   */
  async findUserByEmail(email) {
    const result = await pool.query(
      'SELECT * FROM users WHERE email = $1',
      [email]
    );
    return result.rows[0] || null;
  },

  /**
   * Find a user by ID.
   * @param {string} id UUID
   * @returns {Promise<Object|null>}
   */
  async findUserById(id) {
    const result = await pool.query(
      'SELECT * FROM users WHERE id = $1',
      [id]
    );
    return result.rows[0] || null;
  },

  /**
   * Create a new user.
   * @param {Object} userData
   * @param {string} userData.name
   * @param {string} userData.email
   * @param {string} userData.passwordHash
   * @param {string} [userData.role='user']
   * @returns {Promise<Object>} created user row
   */
  async createUser({ name, email, passwordHash, role = 'user' }) {
    const result = await pool.query(
      `INSERT INTO users (name, email, password_hash, role)
       VALUES ($1, $2, $3, $4)
       RETURNING id, name, email, role, email_verified, created_at`,
      [name, email, passwordHash, role]
    );
    return result.rows[0];
  },

  /**
   * Mark a user's email as verified.
   * @param {string} userId UUID
   * @returns {Promise<Object>}
   */
  async markEmailVerified(userId) {
    const result = await pool.query(
      `UPDATE users SET email_verified = true, updated_at = NOW()
       WHERE id = $1
       RETURNING id, email, email_verified`,
      [userId]
    );
    return result.rows[0];
  },

  /**
   * Update a user's password hash and increment token_version to invalidate prior JWTs.
   * @param {string} userId UUID
   * @param {string} passwordHash
   * @returns {Promise<Object>}
   */
  async updatePassword(userId, passwordHash) {
    const result = await pool.query(
      `UPDATE users
       SET password_hash = $1,
           token_version = token_version + 1,
           updated_at = NOW()
       WHERE id = $2
       RETURNING id, name, email, role, token_version`,
      [passwordHash, userId]
    );
    return result.rows[0];
  },

  /**
   * List users with pagination (excluding password hash).
   * @param {Object} [options]
   * @param {number} [options.limit=50]
   * @param {number} [options.offset=0]
   * @returns {Promise<Array>}
   */
  async listUsers({ limit = 50, offset = 0 } = {}) {
    const result = await pool.query(
      `SELECT id, name, email, role, email_verified, token_version, created_at, updated_at
       FROM users
       ORDER BY created_at DESC
       LIMIT $1 OFFSET $2`,
      [limit, offset]
    );
    return result.rows;
  },

  /**
   * Update a user's role and increment token_version.
   * @param {string} userId
   * @param {string} newRole
   * @returns {Promise<Object>}
   */
  async updateUserRole(userId, newRole) {
    const result = await pool.query(
      `UPDATE users
       SET role = $1,
           token_version = token_version + 1,
           updated_at = NOW()
       WHERE id = $2
       RETURNING id, name, email, role, token_version, updated_at`,
      [newRole, userId]
    );
    return result.rows[0] || null;
  },

  // ─── OTP Queries ──────────────────────────────────────

  /**
   * Create an OTP verification record.
   * @param {Object} otpData
   * @param {string} otpData.userId UUID
   * @param {string} otpData.purpose 'email_verification' | 'password_reset'
   * @param {string} otpData.otpHash SHA-256 hash of the OTP
   * @param {Date} otpData.expiresAt
   * @returns {Promise<Object>}
   */
  async createOtp({ userId, purpose, otpHash, expiresAt }) {
    const result = await pool.query(
      `INSERT INTO otp_verifications (user_id, purpose, otp_hash, expires_at)
       VALUES ($1, $2, $3, $4)
       RETURNING id, user_id, purpose, expires_at, created_at`,
      [userId, purpose, otpHash, expiresAt]
    );
    return result.rows[0];
  },

  /**
   * Find the latest unused, non-expired OTP for a user and purpose.
   * @param {string} userId
   * @param {string} purpose
   * @returns {Promise<Object|null>}
   */
  async findValidOtp(userId, purpose) {
    const result = await pool.query(
      `SELECT * FROM otp_verifications
       WHERE user_id = $1
         AND purpose = $2
         AND used = false
         AND expires_at > NOW()
       ORDER BY created_at DESC
       LIMIT 1`,
      [userId, purpose]
    );
    return result.rows[0] || null;
  },

  /**
   * Find the latest unused OTP for a user and purpose (regardless of expiration).
   * Used to distinguish between expired codes and non-existent codes.
   * @param {string} userId
   * @param {string} purpose
   * @returns {Promise<Object|null>}
   */
  async findLatestOtp(userId, purpose) {
    const result = await pool.query(
      `SELECT * FROM otp_verifications
       WHERE user_id = $1
         AND purpose = $2
         AND used = false
       ORDER BY created_at DESC
       LIMIT 1`,
      [userId, purpose]
    );
    return result.rows[0] || null;
  },

  /**
   * Increment the attempt counter for an OTP record.
   * @param {string} otpId UUID
   * @returns {Promise<void>}
   */
  async incrementOtpAttempts(otpId) {
    await pool.query(
      'UPDATE otp_verifications SET attempts = attempts + 1 WHERE id = $1',
      [otpId]
    );
  },

  /**
   * Mark an OTP as used (single-use).
   * @param {string} otpId UUID
   * @returns {Promise<void>}
   */
  async markOtpUsed(otpId) {
    await pool.query(
      'UPDATE otp_verifications SET used = true WHERE id = $1',
      [otpId]
    );
  },

  /**
   * Invalidate all unused OTPs for a user and purpose.
   * Called before generating a new OTP.
   * @param {string} userId
   * @param {string} purpose
   * @returns {Promise<void>}
   */
  async invalidatePreviousOtps(userId, purpose) {
    await pool.query(
      `UPDATE otp_verifications SET used = true
       WHERE user_id = $1 AND purpose = $2 AND used = false`,
      [userId, purpose]
    );
  },

  // ─── Refresh Token Queries (Remember Me) ──────────────

  /**
   * Store a new hashed refresh token in database.
   * @param {Object} data
   * @param {string} data.userId UUID
   * @param {string} data.tokenHash SHA-256 hash of refresh token
   * @param {Date} data.expiresAt
   * @param {string} [data.userAgent]
   * @param {string} [data.ipAddress]
   * @returns {Promise<Object>}
   */
  async createRefreshToken({ userId, tokenHash, expiresAt, userAgent = null, ipAddress = null }) {
    const result = await pool.query(
      `INSERT INTO refresh_tokens (user_id, token_hash, expires_at, user_agent, ip_address)
       VALUES ($1, $2, $3, $4, $5)
       RETURNING id, user_id, token_hash, expires_at, revoked, created_at`,
      [userId, tokenHash, expiresAt, userAgent, ipAddress]
    );
    return result.rows[0];
  },

  /**
   * Find a refresh token by its SHA-256 hash.
   * @param {string} tokenHash
   * @returns {Promise<Object|null>}
   */
  async findRefreshTokenByHash(tokenHash) {
    const result = await pool.query(
      'SELECT * FROM refresh_tokens WHERE token_hash = $1',
      [tokenHash]
    );
    return result.rows[0] || null;
  },

  /**
   * Revoke a single refresh token by hash.
   * @param {string} tokenHash
   * @returns {Promise<Object|null>}
   */
  async revokeRefreshToken(tokenHash) {
    const result = await pool.query(
      `UPDATE refresh_tokens
       SET revoked = true, updated_at = NOW()
       WHERE token_hash = $1
       RETURNING id, user_id, token_hash, revoked`,
      [tokenHash]
    );
    return result.rows[0] || null;
  },

  /**
   * Revoke all refresh tokens belonging to a specific user.
   * Used on password reset, role changes, or token reuse detection.
   * @param {string} userId UUID
   * @returns {Promise<number>} count of revoked tokens
   */
  async revokeAllUserRefreshTokens(userId) {
    const result = await pool.query(
      `UPDATE refresh_tokens
       SET revoked = true, updated_at = NOW()
       WHERE user_id = $1 AND revoked = false
       RETURNING id`,
      [userId]
    );
    return result.rowCount || 0;
  },

  /**
   * Atomically rotate a refresh token inside a single transaction:
   * 1. Mark old token as revoked
   * 2. Insert new token
   * If old token is already revoked or missing, rollback and return null.
   *
   * @param {Object} params
   * @param {string} params.oldTokenHash
   * @param {string} params.userId
   * @param {string} params.newTokenHash
   * @param {Date} params.expiresAt
   * @param {string} [params.userAgent]
   * @param {string} [params.ipAddress]
   * @returns {Promise<Object|null>}
   */
  async rotateRefreshTokenTransactionally({
    oldTokenHash,
    userId,
    newTokenHash,
    expiresAt,
    userAgent = null,
    ipAddress = null,
  }) {
    const client = await pool.connect();
    try {
      await client.query('BEGIN');

      // Revoke old token atomically
      const revokeRes = await client.query(
        `UPDATE refresh_tokens
         SET revoked = true, updated_at = NOW()
         WHERE token_hash = $1 AND revoked = false
         RETURNING id`,
        [oldTokenHash]
      );

      if (revokeRes.rowCount === 0) {
        await client.query('ROLLBACK');
        return null;
      }

      // Insert new rotated token
      const insertRes = await client.query(
        `INSERT INTO refresh_tokens (user_id, token_hash, expires_at, user_agent, ip_address)
         VALUES ($1, $2, $3, $4, $5)
         RETURNING id, user_id, token_hash, expires_at, revoked, created_at`,
        [userId, newTokenHash, expiresAt, userAgent, ipAddress]
      );

      await client.query('COMMIT');
      return insertRes.rows[0];
    } catch (err) {
      await client.query('ROLLBACK');
      throw err;
    } finally {
      client.release();
    }
  },

  /**
   * Delete expired or old revoked refresh tokens.
   * @returns {Promise<number>} count of deleted rows
   */
  async deleteExpiredRefreshTokens() {
    const result = await pool.query(
      `DELETE FROM refresh_tokens
       WHERE expires_at < NOW() OR revoked = true`
    );
    return result.rowCount || 0;
  },
};

module.exports = authRepository;


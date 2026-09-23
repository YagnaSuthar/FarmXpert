const crypto = require('crypto');
const bcrypt = require('bcrypt');
const { env } = require('../config/env');
const authRepository = require('./auth.repository');
const authOtp = require('./auth.otp');
const authEmail = require('./auth.email');
const authJwt = require('./auth.jwt');
const authSession = require('./auth.session');
const authCaptcha = require('./auth.captcha');

/**
 * In-memory store for short-lived password reset authorizations.
 * Maps resetToken -> { userId, expiresAt, used }
 */
const resetAuthStore = new Map();

/**
 * Auth Service
 *
 * Responsible for authentication business logic:
 * - Registration flow
 * - Email verification flow
 * - Resend verification OTP flow
 * - Login flow (JWT for normal users, in-memory session for privileged users)
 * - Logout flow
 * - CAPTCHA generation & verification
 * - Forgot Password & Password Reset flow
 */

const authService = {
  // ─── Reset Authorization Store Helpers ────────────────

  /**
   * Issue a short-lived, single-use password reset authorization token.
   *
   * @param {string} userId User UUID
   * @returns {string} 64-character hex reset token
   */
  createResetAuthorization(userId) {
    const resetToken = crypto.randomBytes(32).toString('hex');
    const expiresAt = new Date(Date.now() + 5 * 60 * 1000); // 5 minutes validity

    resetAuthStore.set(resetToken, {
      userId,
      expiresAt,
      used: false,
    });

    return resetToken;
  },

  /**
   * Validate and consume a reset authorization token (single-use).
   *
   * @param {string} resetToken
   * @returns {string} User UUID
   */
  validateAndConsumeResetAuthorization(resetToken) {
    if (!resetToken || typeof resetToken !== 'string') {
      const error = new Error('Reset authorization token is required.');
      error.statusCode = 400;
      throw error;
    }

    const record = resetAuthStore.get(resetToken);
    if (!record) {
      const error = new Error('Invalid or expired password reset authorization. Please request a new code.');
      error.statusCode = 400;
      throw error;
    }

    if (record.used) {
      resetAuthStore.delete(resetToken);
      const error = new Error('Password reset authorization has already been used. Please request a new code.');
      error.statusCode = 400;
      throw error;
    }

    if (new Date() > new Date(record.expiresAt)) {
      resetAuthStore.delete(resetToken);
      const error = new Error('Password reset authorization has expired. Please request a new code.');
      error.statusCode = 400;
      throw error;
    }

    // Invalidate immediately upon consumption
    record.used = true;
    resetAuthStore.delete(resetToken);

    return record.userId;
  },

  // ─── Core Authentication Methods ──────────────────────

  /**
   * Helper: Generate a new 6-digit OTP, invalidate previous ones, store hash, and send email.
   *
   * @param {Object} user User record with id and email
   * @param {string} [purpose='email_verification']
   * @returns {Promise<void>}
   */
  async generateAndSendVerificationOtp(user, purpose = 'email_verification') {
    await authRepository.invalidatePreviousOtps(user.id, purpose);
    const otp = authOtp.generateOtp();
    const otpHash = authOtp.hashOtp(otp);
    const expiresAt = authOtp.getExpirationDate();

    await authRepository.createOtp({
      userId: user.id,
      purpose,
      otpHash,
      expiresAt,
    });

    if (purpose === 'password_reset') {
      await authEmail.sendPasswordResetEmail(user.email, otp);
    } else {
      await authEmail.sendVerificationEmail(user.email, otp);
    }
  },

  /**
   * Register a new user and trigger email verification OTP.
   *
   * @param {Object} registrationData
   * @returns {Promise<Object>} Sanitized user object
   */
  async register({ name, email, password, captchaId, captchaAnswer }) {
    if (captchaId) {
      const captchaResult = authCaptcha.verifyCaptcha(captchaId, captchaAnswer);
      if (!captchaResult.isValid) {
        const error = new Error(captchaResult.error || 'Invalid CAPTCHA challenge');
        error.statusCode = 400;
        throw error;
      }
    }

    const existingUser = await authRepository.findUserByEmail(email);
    if (existingUser) {
      const error = new Error('An account with this email already exists');
      error.statusCode = 409;
      throw error;
    }

    const pepperedPassword = password + env.passwordPepper;
    const passwordHash = await bcrypt.hash(pepperedPassword, env.bcryptRounds);

    const createdUser = await authRepository.createUser({
      name,
      email,
      passwordHash,
      role: 'user',
    });

    await this.generateAndSendVerificationOtp(createdUser, 'email_verification');

    return {
      id: createdUser.id,
      name: createdUser.name,
      email: createdUser.email,
      role: createdUser.role,
      email_verified: createdUser.email_verified,
      created_at: createdUser.created_at,
    };
  },

  /**
   * Verify email with 6-digit OTP.
   *
   * @param {Object} verificationData
   * @returns {Promise<{ email: string, email_verified: boolean }>}
   */
  async verifyEmail({ email, otp }) {
    const user = await authRepository.findUserByEmail(email);
    if (!user) {
      const error = new Error('Invalid request or account not found');
      error.statusCode = 400;
      throw error;
    }

    if (user.email_verified) {
      const error = new Error('Email is already verified');
      error.statusCode = 400;
      throw error;
    }

    const otpRecord = await authRepository.findLatestOtp(user.id, 'email_verification');
    if (!otpRecord) {
      const error = new Error('No active verification code found. Please request a new code.');
      error.statusCode = 400;
      throw error;
    }

    if (new Date() > new Date(otpRecord.expires_at)) {
      const error = new Error('Verification code has expired. Please request a new code.');
      error.statusCode = 400;
      throw error;
    }

    const maxAttempts = env.otpMaxAttempts || 5;
    if (otpRecord.attempts >= maxAttempts) {
      const error = new Error('Maximum verification attempts exceeded. Please request a new code.');
      error.statusCode = 400;
      throw error;
    }

    const isValid = authOtp.verifyOtp(otp, otpRecord.otp_hash);

    if (!isValid) {
      await authRepository.incrementOtpAttempts(otpRecord.id);
      const remainingAttempts = maxAttempts - (otpRecord.attempts + 1);

      const message = remainingAttempts > 0
        ? `Invalid verification code. ${remainingAttempts} attempt(s) remaining.`
        : 'Invalid verification code. Maximum attempts reached. Please request a new code.';

      const error = new Error(message);
      error.statusCode = 400;
      throw error;
    }

    await authRepository.markOtpUsed(otpRecord.id);
    await authRepository.markEmailVerified(user.id);

    return {
      email: user.email,
      email_verified: true,
    };
  },

  /**
   * Resend email verification OTP.
   *
   * @param {Object} resendData
   * @returns {Promise<{ message: string }>}
   */
  async resendVerificationOtp({ email }) {
    const user = await authRepository.findUserByEmail(email);

    if (!user || user.email_verified) {
      return {
        message: 'If an unverified account exists for this email, a new verification code has been sent.',
      };
    }

    await this.generateAndSendVerificationOtp(user, 'email_verification');

    return {
      message: 'If an unverified account exists for this email, a new verification code has been sent.',
    };
  },

  /**
   * Authenticate user credentials and select authentication mechanism.
   *
   * @param {Object} credentials
   * @param {string} credentials.email
   * @param {string} credentials.password
   * @param {string} [credentials.captchaId]
   * @param {string} [credentials.captchaAnswer]
   * @param {boolean} [credentials.remember=false]
   * @param {string} [credentials.userAgent]
   * @param {string} [credentials.ipAddress]
   * @returns {Promise<Object>}
   */
  async login({ email, password, captchaId, captchaAnswer, remember = false, userAgent = null, ipAddress = null }) {
    if (captchaId) {
      const captchaResult = authCaptcha.verifyCaptcha(captchaId, captchaAnswer);
      if (!captchaResult.isValid) {
        const error = new Error(captchaResult.error || 'Invalid CAPTCHA challenge');
        error.statusCode = 400;
        throw error;
      }
    }

    const user = await authRepository.findUserByEmail(email);
    if (!user) {
      const error = new Error('Invalid email or password');
      error.statusCode = 401;
      throw error;
    }

    if (!user.email_verified) {
      const error = new Error('Please verify your email address before logging in.');
      error.statusCode = 403;
      throw error;
    }

    const pepperedPassword = password + env.passwordPepper;
    const passwordMatch = await bcrypt.compare(pepperedPassword, user.password_hash);
    if (!passwordMatch) {
      const error = new Error('Invalid email or password');
      error.statusCode = 401;
      throw error;
    }

    const sanitizedUser = {
      id: user.id,
      name: user.name,
      email: user.email,
      role: user.role,
      token_version: user.token_version || 1,
      email_verified: user.email_verified,
      created_at: user.created_at,
    };

    if (authSession.isPrivilegedRole(user.role)) {
      const session = authSession.createSession(user.id, user.role, remember);

      return {
        authType: 'session',
        sessionId: session.sessionId,
        cookieOptions: authSession.getCookieOptions(remember),
        user: sanitizedUser,
        remember: Boolean(remember),
      };
    }

    // Standard user role: always issue 15-minute JWT
    const token = authJwt.generateToken(sanitizedUser);

    // Generate refresh token for standard user (session-scoped if remember is false, 30-day persistent if remember is true)
    const rawRefreshToken = crypto.randomBytes(32).toString('hex');
    const tokenHash = crypto.createHash('sha256').update(rawRefreshToken).digest('hex');
    const maxAgeMs = (env.refreshTokenExpiresDays || 30) * 24 * 60 * 60 * 1000;
    const expiresAt = new Date(Date.now() + (remember ? maxAgeMs : 24 * 60 * 60 * 1000));

    await authRepository.createRefreshToken({
      userId: user.id,
      tokenHash,
      expiresAt,
      userAgent,
      ipAddress,
    });

    const cookieOptions = {
      httpOnly: true,
      secure: env.isProduction,
      sameSite: env.isProduction ? 'strict' : 'lax',
      path: '/',
    };

    if (remember) {
      cookieOptions.maxAge = maxAgeMs;
    }

    return {
      authType: 'jwt',
      token,
      user: sanitizedUser,
      remember: Boolean(remember),
      rawRefreshToken,
      cookieOptions,
    };
  },

  /**
   * Rotate a refresh token and issue a fresh 15-minute JWT.
   *
   * Security rules:
   * 1. Rejects missing or non-string token
   * 2. Hashes token using SHA-256 before lookup
   * 3. Detects token reuse (if token was already revoked, revokes ALL tokens for user)
   * 4. Enforces expiration
   * 5. Atomically rotates old token -> new token inside a transaction
   * 6. Issues new 15-minute JWT
   * 7. Never exposes raw refresh token in JSON response
   *
   * @param {Object} params
   * @param {string} params.rawRefreshToken
   * @param {string} [params.userAgent]
   * @param {string} [params.ipAddress]
   * @returns {Promise<Object>}
   */
  async refreshToken({ rawRefreshToken, userAgent = null, ipAddress = null }) {
    if (!rawRefreshToken || typeof rawRefreshToken !== 'string') {
      const error = new Error('Refresh token is required');
      error.statusCode = 401;
      throw error;
    }

    const tokenHash = crypto.createHash('sha256').update(rawRefreshToken).digest('hex');
    const tokenRecord = await authRepository.findRefreshTokenByHash(tokenHash);

    if (!tokenRecord) {
      const error = new Error('Invalid or expired refresh token');
      error.statusCode = 401;
      throw error;
    }

    // 🚨 REUSE DETECTION / BREACH DEFENSE
    // If an already-revoked refresh token is presented, revoke ALL tokens for this user
    if (tokenRecord.revoked) {
      await authRepository.revokeAllUserRefreshTokens(tokenRecord.user_id);
      const error = new Error('Invalid refresh token: token reuse detected. All sessions revoked.');
      error.statusCode = 401;
      throw error;
    }

    // Check expiration
    if (new Date() > new Date(tokenRecord.expires_at)) {
      await authRepository.revokeRefreshToken(tokenHash);
      const error = new Error('Refresh token has expired. Please log in again.');
      error.statusCode = 401;
      throw error;
    }

    // Load user and verify account state
    const user = await authRepository.findUserById(tokenRecord.user_id);
    if (!user || !user.email_verified || user.role !== 'user') {
      await authRepository.revokeRefreshToken(tokenHash);
      const error = new Error('User account is invalid or unverified.');
      error.statusCode = 401;
      throw error;
    }

    // Perform atomic rotation inside a transaction
    const newRawRefreshToken = crypto.randomBytes(32).toString('hex');
    const newTokenHash = crypto.createHash('sha256').update(newRawRefreshToken).digest('hex');
    const maxAgeMs = (env.refreshTokenExpiresDays || 30) * 24 * 60 * 60 * 1000;
    const newExpiresAt = new Date(Date.now() + maxAgeMs);

    const rotated = await authRepository.rotateRefreshTokenTransactionally({
      oldTokenHash: tokenHash,
      userId: user.id,
      newTokenHash,
      expiresAt: newExpiresAt,
      userAgent,
      ipAddress,
    });

    if (!rotated) {
      const error = new Error('Refresh token already rotated or invalid.');
      error.statusCode = 401;
      throw error;
    }

    const sanitizedUser = {
      id: user.id,
      name: user.name,
      email: user.email,
      role: user.role,
      token_version: user.token_version || 1,
      email_verified: user.email_verified,
      created_at: user.created_at,
    };

    const token = authJwt.generateToken(sanitizedUser);

    return {
      token,
      rawRefreshToken: newRawRefreshToken,
      cookieOptions: {
        httpOnly: true,
        secure: env.isProduction,
        sameSite: env.isProduction ? 'strict' : 'lax',
        path: '/',
        maxAge: maxAgeMs,
      },
      user: sanitizedUser,
    };
  },

  /**
   * Handle user logout by revoking refresh token and/or server session.
   *
   * @param {Object} params
   * @param {string} [params.rawRefreshToken]
   * @param {string} [params.sessionId]
   * @returns {Promise<void>}
   */
  async logout({ rawRefreshToken, sessionId }) {
    if (rawRefreshToken && typeof rawRefreshToken === 'string') {
      const tokenHash = crypto.createHash('sha256').update(rawRefreshToken).digest('hex');
      await authRepository.revokeRefreshToken(tokenHash);
    }

    if (sessionId) {
      authSession.destroySession(sessionId);
    }
  },

  /**
   * Generate a fresh server-side CAPTCHA challenge.
   *
   * @returns {{ captchaId: string, challenge: string, expiresAt: Date }}
   */
  getCaptchaChallenge() {
    return authCaptcha.generateCaptcha();
  },

  // ─── Password Reset Flow ──────────────────────────────

  /**
   * Request password reset code.
   *
   * SECURITY: Always returns a generic response regardless of whether
   * the email exists, preventing user/account enumeration.
   *
   * @param {Object} forgotData
   * @param {string} forgotData.email
   * @param {string} [forgotData.captchaId]
   * @param {string} [forgotData.captchaAnswer]
   * @returns {Promise<{ message: string }>}
   */
  async forgotPassword({ email, captchaId, captchaAnswer }) {
    if (captchaId) {
      const captchaResult = authCaptcha.verifyCaptcha(captchaId, captchaAnswer);
      if (!captchaResult.isValid) {
        const error = new Error(captchaResult.error || 'Invalid CAPTCHA challenge');
        error.statusCode = 400;
        throw error;
      }
    }

    const user = await authRepository.findUserByEmail(email);

    // If account exists, issue reset OTP
    if (user) {
      await this.generateAndSendVerificationOtp(user, 'password_reset');
    }

    // Always return generic response
    return {
      message: 'If an account exists for this email, a password reset code has been sent.',
    };
  },

  /**
   * Verify password reset OTP and issue a short-lived reset authorization token.
   *
   * @param {Object} verifyData
   * @param {string} verifyData.email
   * @param {string} verifyData.otp
   * @returns {Promise<{ resetToken: string, message: string }>}
   */
  async verifyResetOtp({ email, otp }) {
    const user = await authRepository.findUserByEmail(email);
    if (!user) {
      const error = new Error('Invalid request or expired verification code.');
      error.statusCode = 400;
      throw error;
    }

    const otpRecord = await authRepository.findLatestOtp(user.id, 'password_reset');
    if (!otpRecord) {
      const error = new Error('No active password reset request found. Please request a new code.');
      error.statusCode = 400;
      throw error;
    }

    if (new Date() > new Date(otpRecord.expires_at)) {
      const error = new Error('Password reset code has expired. Please request a new code.');
      error.statusCode = 400;
      throw error;
    }

    const maxAttempts = env.otpMaxAttempts || 5;
    if (otpRecord.attempts >= maxAttempts) {
      const error = new Error('Maximum verification attempts exceeded. Please request a new code.');
      error.statusCode = 400;
      throw error;
    }

    const isValid = authOtp.verifyOtp(otp, otpRecord.otp_hash);

    if (!isValid) {
      await authRepository.incrementOtpAttempts(otpRecord.id);
      const remainingAttempts = maxAttempts - (otpRecord.attempts + 1);

      const message = remainingAttempts > 0
        ? `Invalid verification code. ${remainingAttempts} attempt(s) remaining.`
        : 'Invalid verification code. Maximum attempts reached. Please request a new code.';

      const error = new Error(message);
      error.statusCode = 400;
      throw error;
    }

    // Mark OTP used (single-use)
    await authRepository.markOtpUsed(otpRecord.id);

    // Issue short-lived, single-use reset authorization token
    const resetToken = this.createResetAuthorization(user.id);

    return {
      resetToken,
      message: 'Verification code confirmed. Please proceed to set a new password.',
    };
  },

  /**
   * Reset user password using verified reset authorization token.
   *
   * Security actions:
   * 1. Consumes single-use reset authorization token
   * 2. Hashes new password with bcrypt + application pepper
   * 3. Updates password_hash in database
   * 4. Increments token_version in database (instantly invalidating all previously issued JWTs)
   * 5. Revokes all active privileged server-side sessions for this user
   *
   * @param {Object} resetData
   * @param {string} resetData.resetToken
   * @param {string} resetData.newPassword
   * @returns {Promise<{ message: string }>}
   */
  async resetPassword({ resetToken, newPassword }) {
    // 1. Consume single-use reset token and retrieve userId
    const userId = this.validateAndConsumeResetAuthorization(resetToken);

    // 2. Hash new password with bcrypt + pepper
    const pepperedPassword = newPassword + env.passwordPepper;
    const passwordHash = await bcrypt.hash(pepperedPassword, env.bcryptRounds);

    // 3. Update password in database (increments token_version)
    await authRepository.updatePassword(userId, passwordHash);

    // 4. Invalidate all active privileged in-memory sessions
    authSession.destroyUserSessions(userId);

    // 5. Invalidate all active refresh tokens for this user
    await authRepository.revokeAllUserRefreshTokens(userId);

    return {
      message: 'Password has been successfully reset. Please log in with your new password.',
    };
  },

  // ─── User & Role Management Methods ───────────────────

  /**
   * List all users (Admin/SuperAdmin only).
   * @param {Object} [pagination]
   * @returns {Promise<Array>}
   */
  async listUsers(pagination = {}) {
    const limit = Math.min(parseInt(pagination.limit, 10) || 50, 100);
    const offset = Math.max(parseInt(pagination.offset, 10) || 0, 0);
    return authRepository.listUsers({ limit, offset });
  },

  /**
   * Get user details by ID.
   * @param {string} userId
   * @returns {Promise<Object>}
   */
  async getUserById(userId) {
    const user = await authRepository.findUserById(userId);
    if (!user) {
      const error = new Error('User not found');
      error.statusCode = 404;
      throw error;
    }

    return {
      id: user.id,
      name: user.name,
      email: user.email,
      role: user.role,
      email_verified: user.email_verified,
      created_at: user.created_at,
    };
  },

  /**
   * Update user role (SuperAdmin only).
   *
   * @param {Object} params
   * @param {string} params.userId
   * @param {string} params.newRole
   * @returns {Promise<Object>}
   */
  async updateUserRole({ userId, newRole }) {
    const allowedRoles = ['user', 'manager', 'admin', 'super_admin'];
    if (!allowedRoles.includes(newRole)) {
      const error = new Error(`Invalid role '${newRole}'. Allowed roles: ${allowedRoles.join(', ')}`);
      error.statusCode = 400;
      throw error;
    }

    const existingUser = await authRepository.findUserById(userId);
    if (!existingUser) {
      const error = new Error('User not found');
      error.statusCode = 404;
      throw error;
    }

    const updated = await authRepository.updateUserRole(userId, newRole);

    // Invalidate any active sessions for the user to enforce new role login
    authSession.destroyUserSessions(userId);

    // Invalidate any active refresh tokens for the user
    await authRepository.revokeAllUserRefreshTokens(userId);

    return updated;
  },
};

// Periodic background cleanup of expired/revoked refresh tokens every 60 minutes
setInterval(async () => {
  try {
    await authRepository.deleteExpiredRefreshTokens();
  } catch (err) {
    // Ignore background cleanup errors
  }
}, 60 * 60 * 1000).unref();

module.exports = authService;


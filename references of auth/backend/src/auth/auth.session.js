const crypto = require('crypto');
const { env } = require('../config/env');

/**
 * Auth Session Store
 *
 * Server-side session management for privileged users
 * (manager, admin, super_admin).
 *
 * Uses an in-memory Map() for the hackathon.
 *
 * PRODUCTION NOTE:
 * For horizontal scaling / multi-instance deployment,
 * replace Map() with a shared session store such as Redis.
 *
 * Session ID: crypto.randomBytes(32).toString('hex')
 *
 * Session data:
 * {
 *   sessionId,
 *   userId,
 *   role,
 *   createdAt,
 *   expiresAt
 * }
 */

// In-memory session store (hackathon)
const sessionStore = new Map();

// Allowed privileged roles for server-side sessions
const PRIVILEGED_ROLES = ['manager', 'admin', 'super_admin'];

const authSession = {
  /**
   * Check if a role is privileged.
   * @param {string} role
   * @returns {boolean}
   */
  isPrivilegedRole(role) {
    return PRIVILEGED_ROLES.includes(role);
  },

  /**
   * Create a new server-side session for a privileged user.
   * Generates a 32-byte cryptographically secure session ID.
   *
   * @param {string} userId User UUID
   * @param {string} role Privileged role
   * @param {boolean} [remember=false] Extended session lifetime (30 days)
   * @returns {Object} Created session object
   */
  createSession(userId, role, remember = false) {
    if (!this.isPrivilegedRole(role)) {
      throw new Error(`Cannot create privileged session for non-privileged role: ${role}`);
    }

    const sessionId = crypto.randomBytes(32).toString('hex');
    const maxAgeMs = remember
      ? (env.refreshTokenExpiresDays || 30) * 24 * 60 * 60 * 1000
      : (env.sessionMaxAgeMs || 30 * 60 * 1000); // 30 days vs 30 mins
    const now = new Date();
    const expiresAt = new Date(now.getTime() + maxAgeMs);

    const session = {
      sessionId,
      userId,
      role,
      remember: Boolean(remember),
      createdAt: now,
      expiresAt,
    };

    sessionStore.set(sessionId, session);
    return session;
  },

  /**
   * Get an active session by session ID.
   * Automatically removes expired sessions.
   *
   * @param {string} sessionId
   * @returns {Object|null}
   */
  getSession(sessionId) {
    if (!sessionId || typeof sessionId !== 'string') {
      return null;
    }

    const session = sessionStore.get(sessionId);
    if (!session) {
      return null;
    }

    // Check expiration
    if (new Date() > new Date(session.expiresAt)) {
      sessionStore.delete(sessionId);
      return null;
    }

    return session;
  },

  /**
   * Destroy a session by ID (logout).
   * @param {string} sessionId
   * @returns {boolean} True if destroyed
   */
  destroySession(sessionId) {
    if (!sessionId) return false;
    return sessionStore.delete(sessionId);
  },

  /**
   * Destroy all active sessions for a specific user ID.
   * Used for emergency invalidation / password reset.
   *
   * @param {string} userId
   * @returns {number} Number of sessions destroyed
   */
  destroyUserSessions(userId) {
    if (!userId) return 0;

    let count = 0;
    for (const [sid, session] of sessionStore.entries()) {
      if (session.userId === userId) {
        sessionStore.delete(sid);
        count++;
      }
    }
    return count;
  },

  /**
   * Clean up all expired sessions from memory.
   * @returns {number} Count of removed sessions
   */
  cleanExpiredSessions() {
    const now = new Date();
    let removed = 0;

    for (const [sid, session] of sessionStore.entries()) {
      if (now > new Date(session.expiresAt)) {
        sessionStore.delete(sid);
        removed++;
      }
    }
    return removed;
  },

  /**
   * Get secure cookie options for session cookie.
   *
   * @param {boolean} [remember=false]
   * @returns {import('express').CookieOptions}
   */
  getCookieOptions(remember = false) {
    const maxAgeMs = remember
      ? (env.refreshTokenExpiresDays || 30) * 24 * 60 * 60 * 1000
      : (env.sessionMaxAgeMs || 30 * 60 * 1000);
    return {
      httpOnly: true,
      secure: env.isProduction,
      sameSite: env.isProduction ? 'strict' : 'lax',
      maxAge: maxAgeMs,
      path: '/',
    };
  },

  /**
   * Return the in-memory store size (for testing/monitoring).
   */
  getStoreSize() {
    return sessionStore.size;
  },
};

// Periodic background cleanup every 15 minutes
setInterval(() => {
  authSession.cleanExpiredSessions();
}, 15 * 60 * 1000).unref();

module.exports = authSession;

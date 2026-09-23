const { error } = require('../utils/response');
const authJwt = require('./auth.jwt');
const authSession = require('./auth.session');
const authRepository = require('./auth.repository');

/**
 * Auth Middleware
 *
 * Provides:
 * 1. authenticate: Universal authentication for standard JWTs and privileged server sessions
 * 2. authorize(...allowedRoles): Strict role-based access control (RBAC)
 * 3. authorizeOwnerOrRoles(getOwnerIdFn, ...privilegedRoles): Resource ownership authorization
 *
 * Security rules:
 * - 401 Unauthorized: Returned when authentication token/session is missing, expired, or invalid
 * - 403 Forbidden: Returned when authenticated user lacks required role permissions or resource ownership
 * - Never trusts client-supplied roles from body/headers/query; uses only server-verified req.user.role
 */

const authMiddleware = {
  /**
   * Universal authentication middleware.
   * Auto-detects and validates either privileged session cookie or user JWT.
   */
  async authenticate(req, res, next) {
    try {
      const sessionCookie = req.cookies?.sid;
      const authHeader = req.headers?.authorization;

      // ─── Path 1: Server-Side Session (Privileged Users) ───
      if (sessionCookie) {
        const session = authSession.getSession(sessionCookie);
        if (!session) {
          return error(res, 'Session has expired or is invalid. Please log in again.', 401);
        }

        // Fetch fresh user record from database
        const user = await authRepository.findUserById(session.userId);
        if (!user) {
          authSession.destroySession(sessionCookie);
          return error(res, 'User account not found', 401);
        }

        // Enforce privileged role
        if (!authSession.isPrivilegedRole(user.role)) {
          authSession.destroySession(sessionCookie);
          return error(res, 'Invalid session privileges', 403);
        }

        // Enforce email verification
        if (!user.email_verified) {
          return error(res, 'Email verification required', 403);
        }

        // Attach user info to request
        req.user = {
          id: user.id,
          name: user.name,
          email: user.email,
          role: user.role,
          token_version: user.token_version,
          email_verified: user.email_verified,
          created_at: user.created_at,
        };
        req.authType = 'session';
        req.sessionId = sessionCookie;

        return next();
      }

      // ─── Path 2: JWT Bearer Token (Standard Users) ────────
      if (authHeader && authHeader.startsWith('Bearer ')) {
        const token = authHeader.substring(7).trim();
        if (!token) {
          return error(res, 'Access token missing', 401);
        }

        let payload;
        try {
          payload = authJwt.verifyToken(token);
        } catch (jwtErr) {
          if (jwtErr.name === 'TokenExpiredError') {
            return error(res, 'Access token has expired', 401);
          }
          return error(res, 'Invalid access token', 401);
        }

        if (!payload.sub || payload.role !== 'user') {
          return error(res, 'Invalid token payload', 401);
        }

        // Fetch fresh user record from database
        const user = await authRepository.findUserById(payload.sub);
        if (!user) {
          return error(res, 'User account not found', 401);
        }

        // Enforce that user is indeed a standard user (not elevated)
        if (user.role !== 'user') {
          return error(res, 'Role mismatch: privileged roles must authenticate via server session', 403);
        }

        // Enforce token version consistency (invalidates JWT immediately after password reset)
        if (payload.tokenVersion !== undefined && payload.tokenVersion !== user.token_version) {
          return error(res, 'Access token has been revoked. Please log in again.', 401);
        }

        // Enforce email verification
        if (!user.email_verified) {
          return error(res, 'Email verification required', 403);
        }

        // Attach user info to request
        req.user = {
          id: user.id,
          name: user.name,
          email: user.email,
          role: user.role,
          token_version: user.token_version,
          email_verified: user.email_verified,
          created_at: user.created_at,
        };
        req.authType = 'jwt';
        req.jwtPayload = payload;

        return next();
      }

      // ─── Path 3: Neither provided ─────────────────────────
      return error(res, 'Authentication required. Please provide a valid session or token.', 401);
    } catch (err) {
      next(err);
    }
  },

  /**
   * Role-Based Access Control (RBAC) middleware.
   * Checks if authenticated user has one of the explicitly allowed roles.
   *
   * @param {...string} allowedRoles List of roles permitted to access endpoint
   * @returns {import('express').RequestHandler}
   */
  authorize(...allowedRoles) {
    return (req, res, next) => {
      // 1. Verify user is authenticated
      if (!req.user || !req.user.role) {
        return error(res, 'Authentication required before authorization.', 401);
      }

      // 2. Explicit role check
      if (!allowedRoles.includes(req.user.role)) {
        return error(
          res,
          `Access denied: role '${req.user.role}' is not authorized to access this resource.`,
          403
        );
      }

      return next();
    };
  },

  /**
   * Resource Ownership Authorization middleware.
   * Enforces that standard users can ONLY access their own resources,
   * while allowing specified privileged roles (e.g. admin, super_admin) if requested.
   *
   * @param {function(import('express').Request): string} getOwnerIdFn Function extracting resource owner UUID from request
   * @param {...string} privilegedRoles Optional roles that bypass ownership (e.g. 'admin', 'super_admin')
   * @returns {import('express').RequestHandler}
   */
  authorizeOwnerOrRoles(getOwnerIdFn, ...privilegedRoles) {
    return (req, res, next) => {
      if (!req.user || !req.user.id) {
        return error(res, 'Authentication required before authorization.', 401);
      }

      const resourceOwnerId = typeof getOwnerIdFn === 'function'
        ? getOwnerIdFn(req)
        : req.params.id;

      // Case 1: Authenticated user owns the resource
      if (req.user.id === resourceOwnerId) {
        return next();
      }

      // Case 2: User holds a privileged role authorized to view other users' resources
      if (privilegedRoles.length > 0 && privilegedRoles.includes(req.user.role)) {
        return next();
      }

      // Case 3: Forbidden (prevent Horizontal Privilege Escalation / IDOR)
      return error(res, 'Access denied: you do not own this resource.', 403);
    };
  },
};

module.exports = authMiddleware;

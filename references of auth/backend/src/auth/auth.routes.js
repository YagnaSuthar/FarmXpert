const express = require('express');
const rateLimit = require('express-rate-limit');
const { env } = require('../config/env');
const { error } = require('../utils/response');
const authController = require('./auth.controller');
const authMiddleware = require('./auth.middleware');

const router = express.Router();

/**
 * Rate Limiters for Auth Feature
 */

// Stricter rate limiter for OTP verification and generation (resend)
const otpRateLimiter = rateLimit({
  windowMs: env.authRateLimitWindowMs || 15 * 60 * 1000,
  max: env.authRateLimitMax || 30,
  standardHeaders: true,
  legacyHeaders: false,
  handler: (req, res) => {
    return error(res, 'Too many OTP requests from this IP, please try again later.', 429);
  },
});

// Auth rate limiter (register, login, etc.)
const authRateLimiter = rateLimit({
  windowMs: env.authRateLimitWindowMs || 15 * 60 * 1000,
  max: env.authRateLimitMax || 10,
  standardHeaders: true,
  legacyHeaders: false,
  handler: (req, res) => {
    return error(res, 'Too many requests, please try again later.', 429);
  },
});

// CAPTCHA rate limiter
const captchaRateLimiter = rateLimit({
  windowMs: env.authRateLimitWindowMs || 15 * 60 * 1000,
  max: (env.authRateLimitMax || 10) * 3,
  standardHeaders: true,
  legacyHeaders: false,
  handler: (req, res) => {
    return error(res, 'Too many CAPTCHA requests from this IP, please try again later.', 429);
  },
});

/**
 * Auth Routes
 *
 * Public routes:
 * POST /register              — Register a new user + send verification OTP
 * POST /verify-email          — Verify email with 6-digit OTP
 * POST /resend-verification-otp — Resend email verification OTP
 * POST /login                 — Authenticate (JWT for user, session cookie for privileged)
 * GET  /captcha               — Generate CAPTCHA challenge
 * POST /forgot-password       — Request password reset OTP
 * POST /verify-reset-otp      — Verify password reset OTP
 * POST /reset-password        — Reset password with verified OTP
 *
 * Protected user routes:
 * POST /logout                — Invalidate session / clear cookies
 * GET  /me                    — Retrieve current authenticated profile
 * GET  /users/:id             — Resource ownership protected endpoint (owner OR admin/super_admin)
 *
 * Protected privileged routes (RBAC):
 * GET  /manager/dashboard     — Manager / Admin / SuperAdmin only
 * GET  /admin/users           — Admin / SuperAdmin only
 * PATCH /admin/users/:id/role — SuperAdmin only
 */

// Public endpoints
router.post('/register', authRateLimiter, authController.register);
router.post('/verify-email', otpRateLimiter, authController.verifyEmail);
router.post('/resend-verification-otp', otpRateLimiter, authController.resendVerificationOtp);
router.post('/login', authRateLimiter, authController.login);
router.post('/refresh', authRateLimiter, authController.refresh);
router.get('/captcha', captchaRateLimiter, authController.getCaptcha);

router.post('/forgot-password', otpRateLimiter, authController.forgotPassword);
router.post('/verify-reset-otp', otpRateLimiter, authController.verifyResetOtp);
router.post('/reset-password', authRateLimiter, authController.resetPassword);

// Logout (can be called by any client to revoke cookies & session)
router.post('/logout', authController.logout);

// Protected authenticated routes
router.get('/me', authMiddleware.authenticate, authController.getMe);

// Resource Ownership Protected Route (Owner OR admin/super_admin)
router.get(
  '/users/:id',
  authMiddleware.authenticate,
  authMiddleware.authorizeOwnerOrRoles((req) => req.params.id, 'admin', 'super_admin'),
  authController.getUserProfileById
);

// Privileged Role-Protected Routes (RBAC)
router.get(
  '/manager/dashboard',
  authMiddleware.authenticate,
  authMiddleware.authorize('manager', 'admin', 'super_admin'),
  authController.getManagerDashboard
);

router.get(
  '/admin/users',
  authMiddleware.authenticate,
  authMiddleware.authorize('admin', 'super_admin'),
  authController.listUsers
);

router.patch(
  '/admin/users/:id/role',
  authMiddleware.authenticate,
  authMiddleware.authorize('super_admin'),
  authController.updateUserRole
);

module.exports = router;

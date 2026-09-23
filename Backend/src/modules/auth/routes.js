/**
 * /api/v1/auth
 *
 * Public:   captcha, register, verify-email, resend-code, login, refresh,
 *           forgot-password, verify-reset-code, reset-password, logout
 * Signed in: me (GET/PATCH), change-password, logout-everywhere
 * Staff:    admin/users/:id/role (super_admin)
 *
 * Tokens: the access token is returned in the body and kept in memory by the
 * app; the refresh token is an HttpOnly cookie scoped to this path.
 */

import { Router } from 'express';

import { config } from '../../config/env.js';
import { one, transaction } from '../../db/pool.js';
import { notFound } from '../../lib/errors.js';
import { rateLimit } from '../../lib/rateLimit.js';
import { idParam, validate } from '../../lib/validate.js';
import { authenticate, requireRole } from './middleware.js';
import { EMAIL_PATTERN } from './security.js';
import * as auth from './service.js';
import {
  REFRESH_COOKIE, refreshCookieOptions, revokeEverything, revokeRefreshToken, rotateRefreshToken,
  signAccessToken,
} from './tokens.js';

export const authRoutes = Router();

// Per IP (the user is not known before login), 15-minute windows, one budget
// per action: a farmer registering must not use up their own login attempts.
const FIFTEEN_MIN = 15 * 60_000;
const base = config.auth.rateLimitPer15Min;
const limiter = (name, factor) => rateLimit({ limit: Math.max(1, Math.round(base * factor)), windowMs: FIFTEEN_MIN, name });
const loginGuard = limiter('auth-login', 1);          // 20 by default
const registerGuard = limiter('auth-register', 0.5);  // 10
const captchaGuard = limiter('auth-captcha', 3);      // 60
const codeGuard = limiter('auth-code', 1);            // 20: codes, resends, resets
const guard = limiter('auth-account', 1);             // signed-in account changes

const email = { type: 'string', maxLength: 255, pattern: EMAIL_PATTERN };
const password = { type: 'string', minLength: 1, maxLength: 128 };
const code = { type: 'string', pattern: '^[0-9]{6}$' };
const captcha = {
  captcha_id: { type: 'string', maxLength: 128 },
  captcha_answer: { type: ['string', 'number'] },
};
const body = (properties, required) => ({ body: { type: 'object', properties, required } });

function sendSession(res, result, status = 200) {
  res.cookie(REFRESH_COOKIE, result.refresh.raw,
    refreshCookieOptions(result.refresh.maxAgeMs, result.refresh.persistent));
  res.status(status).json({
    user: result.user,
    access_token: result.accessToken,
    expires_in_s: config.auth.accessTtlSeconds,
  });
}

function clearSession(res) {
  const { maxAge, ...options } = refreshCookieOptions(0, false);
  res.clearCookie(REFRESH_COOKIE, options);
}

const client = (req) => ({ userAgent: req.get('user-agent') || null, ip: req.ip });

authRoutes.get('/auth/captcha', captchaGuard, async (req, res) => {
  res.set('Cache-Control', 'no-store').json(await auth.newCaptcha());
});

authRoutes.post('/auth/register', registerGuard, validate(body({
  name: { type: 'string', minLength: 2, maxLength: 120 },
  email,
  password,
  phone: { type: 'string', pattern: '^[0-9+][0-9]{7,14}$' },
  language: { type: 'string', maxLength: 12 },
  ...captcha,
}, ['name', 'email', 'password', 'captcha_id', 'captcha_answer'])), async (req, res) => {
  const result = await auth.register(req.body);
  res.status(201).json({ ...result, next: 'verify_email' });
});

authRoutes.post('/auth/verify-email', codeGuard, validate(body({ email, code }, ['email', 'code'])),
  async (req, res) => {
    res.json(await auth.verifyEmail(req.body));
  });

// Always the same answer: whether the address is registered stays private.
authRoutes.post('/auth/resend-code', codeGuard, validate(body({ email }, ['email'])), async (req, res) => {
  await auth.resendVerification(req.body);
  res.json({ message: 'If an unverified account uses this email, a new code is on its way.' });
});

authRoutes.post('/auth/login', loginGuard, validate(body({
  email, password, remember: { type: 'boolean', default: false }, ...captcha,
}, ['email', 'password'])), async (req, res) => {
  sendSession(res, await auth.login(req.body, client(req)));
});

authRoutes.post('/auth/refresh', async (req, res) => {
  const result = await rotateRefreshToken(req.cookies?.[REFRESH_COOKIE], client(req));
  if (result.error) {
    clearSession(res);
    res.status(401).json({ error: {
      code: result.error === 'reused' ? 'session_revoked' : 'session_expired',
      message: 'Please log in again.',
    } });
    return;
  }
  sendSession(res, { user: auth.publicUser(result.user), accessToken: signAccessToken(result.user),
    refresh: { raw: result.raw, maxAgeMs: result.maxAgeMs, persistent: result.persistent } });
});

authRoutes.post('/auth/logout', async (req, res) => {
  await revokeRefreshToken(req.cookies?.[REFRESH_COOKIE]);
  clearSession(res);
  res.status(204).end();
});

authRoutes.post('/auth/forgot-password', codeGuard, validate(body({ email, ...captcha },
  ['email', 'captcha_id', 'captcha_answer'])), async (req, res) => {
  await auth.forgotPassword(req.body);
  res.json({ message: 'If an account uses this email, a reset code is on its way.' });
});

authRoutes.post('/auth/verify-reset-code', codeGuard, validate(body({ email, code }, ['email', 'code'])),
  async (req, res) => {
    res.json(await auth.verifyResetCode(req.body));
  });

authRoutes.post('/auth/reset-password', codeGuard, validate(body({
  reset_token: { type: 'string', minLength: 64, maxLength: 64 }, password,
}, ['reset_token', 'password'])), async (req, res) => {
  await auth.resetPassword(req.body);
  clearSession(res);
  res.json({ message: 'Password changed. Please log in with your new password.' });
});

// ── signed in ───────────────────────────────────────────────────────────────

authRoutes.get('/auth/me', authenticate, async (req, res) => {
  const user = await one(
    `SELECT id, name, email, phone, language, role, email_verified, onboarded_at, created_at
       FROM users WHERE id = $1`, [req.user.id],
  );
  res.set('Cache-Control', 'no-store').json({ user: auth.publicUser(user) });
});

authRoutes.patch('/auth/me', authenticate, validate(body({
  name: { type: 'string', minLength: 2, maxLength: 120 },
  phone: { type: 'string', pattern: '^[0-9+][0-9]{7,14}$' },
  language: { type: 'string', maxLength: 12 },
})), async (req, res) => {
  const { name = null, phone = null, language = null } = req.body;
  const user = await one(
    `UPDATE users SET name = COALESCE($2, name), phone = COALESCE($3, phone), language = COALESCE($4, language)
      WHERE id = $1 RETURNING id, name, email, phone, language, role, email_verified, onboarded_at, created_at`,
    [req.user.id, name?.trim() ?? null, phone, language],
  );
  res.json({ user: auth.publicUser(user) });
});

authRoutes.post('/auth/change-password', authenticate, guard, validate(body({
  current_password: password, password,
}, ['current_password', 'password'])), async (req, res) => {
  await auth.changePassword(req.user.id, req.body);
  clearSession(res);
  res.json({ message: 'Password changed. Please log in again on your devices.' });
});

authRoutes.post('/auth/logout-everywhere', authenticate, async (req, res) => {
  await transaction((db) => revokeEverything(db, req.user.id));
  clearSession(res);
  res.status(204).end();
});

authRoutes.patch('/auth/admin/users/:id/role', authenticate, requireRole('super_admin'), validate({
  params: idParam,
  body: { type: 'object', properties: { role: { enum: ['farmer', 'agronomist', 'admin', 'super_admin'] } }, required: ['role'] },
}), async (req, res) => {
  const user = await auth.setRole(req.params.id, req.body.role);
  if (!user) throw notFound('User');
  res.json({ user });
});

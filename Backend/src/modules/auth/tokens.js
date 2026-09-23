/**
 * Access tokens (JWT) and refresh tokens.
 *
 * Access: HS256, 15 minutes, { sub, role, tv }. `tv` is the user's
 * token_version: bumping it (password reset, role change, "log out
 * everywhere") makes every outstanding access token invalid at once.
 *
 * Refresh: opaque 32 bytes in an HttpOnly cookie scoped to /api/v1/auth, so
 * it is sent only to the refresh and logout endpoints and no script can read
 * it. Rotated on every use. Presenting a token that was already rotated means
 * it was copied - the whole login family is revoked.
 */

import { randomUUID } from 'node:crypto';

import jwt from 'jsonwebtoken';

import { config } from '../../config/env.js';
import { query, transaction } from '../../db/pool.js';
import { newOpaqueToken, sha256 } from './security.js';

const ISSUER = 'farmxpert';
const AUDIENCE = 'farmxpert-app';
export const PRIVILEGED = new Set(['admin', 'super_admin']);
export const REFRESH_COOKIE = 'fx_refresh';

export function signAccessToken(user) {
  return jwt.sign({ role: user.role, tv: user.token_version }, config.auth.jwtSecret, {
    subject: user.id,
    expiresIn: config.auth.accessTtlSeconds,
    issuer: ISSUER,
    audience: AUDIENCE,
    algorithm: 'HS256',
  });
}

/** The verified payload, or null. Never throws. */
export function verifyAccessToken(token) {
  try {
    return jwt.verify(token, config.auth.jwtSecret, {
      issuer: ISSUER, audience: AUDIENCE, algorithms: ['HS256'],
    });
  } catch {
    return null;
  }
}

function refreshLifetimeMs(user, persistent) {
  if (PRIVILEGED.has(user.role)) return config.auth.privilegedRefreshHours * 3600_000;
  return persistent ? config.auth.refreshDays * 86_400_000 : 86_400_000;
}

export function refreshCookieOptions(maxAgeMs, persistent) {
  return {
    httpOnly: true,
    secure: config.auth.cookieSecure,
    sameSite: 'lax',
    path: '/api/v1/auth',
    domain: config.auth.cookieDomain,
    // Not "remember me": a browser-session cookie, gone when the browser closes.
    ...(persistent ? { maxAge: maxAgeMs } : {}),
  };
}

/** Start a new login family. Returns { raw, maxAgeMs, persistent }. */
export async function issueRefreshToken(db, user, { persistent, userAgent, ip }) {
  const raw = newOpaqueToken();
  const keep = persistent && !PRIVILEGED.has(user.role);
  const maxAgeMs = refreshLifetimeMs(user, keep);
  await db.query(
    `INSERT INTO refresh_tokens (user_id, family_id, token_hash, expires_at, persistent, user_agent, ip_address)
     VALUES ($1, $2, $3, now() + $4 * interval '1 millisecond', $5, $6, $7)`,
    [user.id, randomUUID(), sha256(raw), maxAgeMs, keep, userAgent?.slice(0, 300) ?? null, ip?.slice(0, 64) ?? null],
  );
  return { raw, maxAgeMs, persistent: keep };
}

/**
 * Swap a refresh token for a new one. Returns { user, raw, maxAgeMs, persistent }
 * or { error } - 'missing' | 'invalid' | 'reused' | 'expired' | 'account'.
 */
export async function rotateRefreshToken(raw, { userAgent, ip }) {
  if (!raw || typeof raw !== 'string' || raw.length > 200) return { error: 'missing' };
  return transaction(async (db) => {
    // FOR UPDATE: two tabs refreshing at once must not both rotate one token.
    const { rows } = await db.query(
      `SELECT t.id, t.family_id, t.expires_at, t.revoked_at, t.persistent,
              u.id AS user_id, u.name, u.email, u.role, u.token_version, u.email_verified,
              u.language, u.onboarded_at, u.deleted_at
         FROM refresh_tokens t JOIN users u ON u.id = t.user_id
        WHERE t.token_hash = $1
          FOR UPDATE OF t`,
      [sha256(raw)],
    );
    const row = rows[0];
    if (!row) return { error: 'invalid' };
    if (row.revoked_at) {
      // A rotated token came back: someone else has it. End every session of
      // this login, on every device.
      await db.query(
        'UPDATE refresh_tokens SET revoked_at = now() WHERE family_id = $1 AND revoked_at IS NULL',
        [row.family_id],
      );
      return { error: 'reused' };
    }
    if (new Date(row.expires_at) <= new Date()) {
      await db.query('UPDATE refresh_tokens SET revoked_at = now() WHERE id = $1', [row.id]);
      return { error: 'expired' };
    }
    if (row.deleted_at || !row.email_verified) return { error: 'account' };

    const user = {
      id: row.user_id, name: row.name, email: row.email, role: row.role,
      token_version: row.token_version, email_verified: row.email_verified,
      language: row.language, onboarded_at: row.onboarded_at,
    };
    const next = newOpaqueToken();
    const maxAgeMs = refreshLifetimeMs(user, row.persistent);
    await db.query('UPDATE refresh_tokens SET revoked_at = now() WHERE id = $1', [row.id]);
    await db.query(
      `INSERT INTO refresh_tokens (user_id, family_id, token_hash, expires_at, persistent, user_agent, ip_address)
       VALUES ($1, $2, $3, now() + $4 * interval '1 millisecond', $5, $6, $7)`,
      [user.id, row.family_id, sha256(next), maxAgeMs, row.persistent,
        userAgent?.slice(0, 300) ?? null, ip?.slice(0, 64) ?? null],
    );
    return { user, raw: next, maxAgeMs, persistent: row.persistent };
  });
}

export async function revokeRefreshToken(raw) {
  if (!raw || typeof raw !== 'string') return;
  await query('UPDATE refresh_tokens SET revoked_at = now() WHERE token_hash = $1 AND revoked_at IS NULL', [sha256(raw)]);
}

/** Every device, every access token: used by password reset and role changes. */
export async function revokeEverything(db, userId) {
  await db.query('UPDATE users SET token_version = token_version + 1 WHERE id = $1', [userId]);
  await db.query('UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = $1 AND revoked_at IS NULL', [userId]);
}

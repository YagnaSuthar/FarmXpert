/**
 * Who is calling, and may they?
 *
 *   authenticate      a valid access token is required; sets req.user
 *   optionalAuth      sets req.user when a token is present, never refuses
 *   requireRole(...)  401 without a user, 403 with the wrong role
 *   requireFarm(src)  the farm in the request must belong to req.user (or the
 *                     caller is staff) - the IDOR guard for every farm route
 *
 * The token is checked against the database on every request (one primary-
 * key lookup): a deleted account, a changed role or a bumped token_version
 * takes effect immediately rather than when the token expires.
 */

import { one } from '../../db/pool.js';
import { HttpError, notFound, unauthorized } from '../../lib/errors.js';
import { verifyAccessToken } from './tokens.js';

export const STAFF = new Set(['agronomist', 'admin', 'super_admin']);

async function resolveUser(req) {
  const header = req.get('authorization') || '';
  if (!header.startsWith('Bearer ')) return { missing: true };
  const payload = verifyAccessToken(header.slice(7).trim());
  if (!payload?.sub) return { invalid: true };
  const user = await one(
    `SELECT id, name, email, role, token_version, email_verified, language, onboarded_at
       FROM users WHERE id = $1 AND deleted_at IS NULL`,
    [payload.sub],
  );
  if (!user || user.token_version !== payload.tv || !user.email_verified) return { invalid: true };
  return { user };
}

export async function authenticate(req, res, next) {
  try {
    const { user, missing } = await resolveUser(req);
    if (!user) {
      return next(new HttpError(401, missing ? 'auth_required' : 'token_invalid',
        missing ? 'Please log in.' : 'Your session has ended. Please log in again.'));
    }
    req.user = user;
    return next();
  } catch (err) {
    return next(err);
  }
}

export async function optionalAuth(req, res, next) {
  try {
    const { user, invalid } = await resolveUser(req);
    // A token that is present but bad is refused: silently treating the
    // caller as anonymous would hide an expired session from the app.
    if (invalid) return next(new HttpError(401, 'token_invalid', 'Your session has ended. Please log in again.'));
    if (user) req.user = user;
    return next();
  } catch (err) {
    return next(err);
  }
}

export function requireRole(...roles) {
  return (req, res, next) => {
    if (!req.user) return next(unauthorized('Please log in.'));
    if (!roles.includes(req.user.role)) return next(new HttpError(403, 'forbidden', 'You do not have access to this.'));
    return next();
  };
}

/**
 * Ownership check for a farm named by the request. `from` picks the id:
 * 'params' (default, :id), 'body' (farm_id), 'query' (farm_id).
 * Staff may read any farm. A farm that exists but is not yours answers 404,
 * not 403: whether someone else's farm exists is not yours to learn.
 */
export function requireFarm(from = 'params', key = from === 'params' ? 'id' : 'farm_id') {
  return async (req, res, next) => {
    try {
      if (!req.user) return next(unauthorized('Please log in.'));
      const farmId = req[from]?.[key];
      if (!farmId) return next();
      const farm = await one('SELECT user_id FROM farms WHERE id = $1 AND deleted_at IS NULL', [farmId]);
      if (!farm || (farm.user_id !== req.user.id && !STAFF.has(req.user.role))) return next(notFound('Farm'));
      return next();
    } catch (err) {
      return next(err);
    }
  };
}

/** Ownership for rows that hang off a farm (fields, tasks, plans, devices). */
export function requireOwned(table, param = 'id') {
  const allowed = new Set(['fields', 'scheduled_tasks', 'irrigation_plans', 'blynk_tokens']);
  if (!allowed.has(table)) throw new Error(`requireOwned: unsupported table ${table}`);
  return async (req, res, next) => {
    try {
      if (!req.user) return next(unauthorized('Please log in.'));
      const row = await one(
        `SELECT f.user_id FROM ${table} t JOIN farms f ON f.id = t.farm_id WHERE t.id = $1`,
        [req.params[param]],
      );
      if (!row || (row.user_id !== req.user.id && !STAFF.has(req.user.role))) {
        return next(notFound('Record'));
      }
      return next();
    } catch (err) {
      return next(err);
    }
  };
}

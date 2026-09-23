/**
 * Account lifecycle: register -> verify email -> log in -> refresh -> log out,
 * and forgot password -> verify code -> reset.
 *
 * Every answer that could reveal whether an email is registered is generic
 * ("if an account exists..."), and unknown emails cost the same bcrypt time
 * as wrong passwords, so accounts cannot be enumerated.
 */

import { config } from '../../config/env.js';
import { one, query, transaction } from '../../db/pool.js';
import { HttpError, badRequest, conflict } from '../../lib/errors.js';
import { sendCode } from './mail.js';
import {
  hashPassword, hmac, newOpaqueToken, newOtp, normaliseEmail, passwordProblems, sameHex, sha256,
  verifyPassword,
} from './security.js';
import { issueRefreshToken, revokeEverything, signAccessToken } from './tokens.js';

const CAPTCHA_AFTER_FAILURES = 3;
const LOCK_AFTER_FAILURES = 10;
const LOCK_MINUTES = 15;
const RESET_AUTH_MINUTES = 5;

const USER_COLUMNS = `id, name, email, phone, language, role, email_verified, token_version,
  onboarded_at, created_at`;

/** What the app may know about its own user. */
export function publicUser(u) {
  return {
    id: u.id, name: u.name, email: u.email, phone: u.phone ?? null, language: u.language,
    role: u.role, email_verified: u.email_verified, onboarded: Boolean(u.onboarded_at),
    created_at: u.created_at,
  };
}

const fail = (status, code, message, details) => new HttpError(status, code, message, details);

// ── captcha ─────────────────────────────────────────────────────────────────

export async function newCaptcha() {
  const { randomInt } = await import('node:crypto');
  const op = randomInt(0, 3);
  let a;
  let b;
  let answer;
  let symbol;
  if (op === 0) { a = randomInt(10, 50); b = randomInt(5, 30); answer = a + b; symbol = '+'; }
  else if (op === 1) { a = randomInt(30, 80); b = randomInt(5, a); answer = a - b; symbol = '−'; }
  else { a = randomInt(2, 10); b = randomInt(2, 10); answer = a * b; symbol = '×'; }
  const id = newOpaqueToken();
  await query(
    `INSERT INTO auth_challenges (id, kind, secret_hash, expires_at)
     VALUES ($1, 'captcha', $2, now() + $3 * interval '1 minute')`,
    [sha256(id), hmac(answer), config.auth.captchaMinutes],
  );
  return { captcha_id: id, challenge: `${a} ${symbol} ${b} = ?`, expires_in_s: config.auth.captchaMinutes * 60 };
}

/** Consume a captcha. Throws 400 with a clear code when it does not pass. */
async function checkCaptcha(id, answer) {
  if (!id || answer === undefined || answer === null || String(answer).trim() === '') {
    throw fail(400, 'captcha_required', 'Please solve the security question.');
  }
  const key = sha256(id);
  const row = await one(
    `UPDATE auth_challenges SET attempts = attempts + 1
      WHERE id = $1 AND kind = 'captcha' AND expires_at > now()
      RETURNING secret_hash, attempts`,
    [key],
  );
  if (!row) throw fail(400, 'captcha_expired', 'The security question expired. Please try a new one.');
  if (sameHex(hmac(String(answer).trim()), row.secret_hash)) {
    await query('DELETE FROM auth_challenges WHERE id = $1', [key]);     // single use
    return;
  }
  if (row.attempts >= 3) await query('DELETE FROM auth_challenges WHERE id = $1', [key]);
  throw fail(400, 'captcha_wrong', 'That answer is not right. Please try again.');
}

// ── one-time codes ──────────────────────────────────────────────────────────

async function issueCode(db, user, purpose) {
  // A new code replaces any earlier one for the same purpose.
  await db.query('UPDATE otp_verifications SET used = true WHERE user_id = $1 AND purpose = $2 AND NOT used',
    [user.id, purpose]);
  const code = newOtp();
  await db.query(
    `INSERT INTO otp_verifications (user_id, purpose, otp_hash, expires_at)
     VALUES ($1, $2, $3, now() + $4 * interval '1 minute')`,
    [user.id, purpose, hmac(code), config.auth.otpMinutes],
  );
  return code;
}

/** Check and consume the newest live code. Throws with remaining attempts. */
async function consumeCode(userId, purpose, code) {
  // The outcome is decided inside the transaction but thrown after it commits:
  // throwing inside would roll back the attempt counter and void the limit.
  const outcome = await transaction(async (db) => {
    const { rows } = await db.query(
      `SELECT id, otp_hash, expires_at, attempts FROM otp_verifications
        WHERE user_id = $1 AND purpose = $2 AND NOT used
        ORDER BY created_at DESC LIMIT 1 FOR UPDATE`,
      [userId, purpose],
    );
    const otp = rows[0];
    if (!otp) return { error: fail(400, 'code_missing', 'No active code. Please ask for a new one.') };
    if (new Date(otp.expires_at) <= new Date()) {
      return { error: fail(400, 'code_expired', 'The code has expired. Please ask for a new one.') };
    }
    if (otp.attempts >= config.auth.otpMaxAttempts) {
      return { error: fail(400, 'code_locked', 'Too many wrong tries. Please ask for a new code.') };
    }
    if (!sameHex(hmac(String(code)), otp.otp_hash)) {
      await db.query('UPDATE otp_verifications SET attempts = attempts + 1 WHERE id = $1', [otp.id]);
      const left = config.auth.otpMaxAttempts - otp.attempts - 1;
      return {
        error: fail(400, left > 0 ? 'code_wrong' : 'code_locked',
          left > 0 ? 'That code is not right.' : 'Too many wrong tries. Please ask for a new code.',
          { attempts_left: Math.max(0, left) }),
      };
    }
    await db.query('UPDATE otp_verifications SET used = true WHERE id = $1', [otp.id]);
    return {};
  });
  if (outcome.error) throw outcome.error;
}

// ── flows ───────────────────────────────────────────────────────────────────

export async function register({ name, email, password, phone, language, captcha_id, captcha_answer }) {
  const problems = passwordProblems(password);
  if (problems.length) throw fail(422, 'weak_password', 'Choose a stronger password.', { problems });
  await checkCaptcha(captcha_id, captcha_answer);
  const address = normaliseEmail(email);
  const passwordHash = await hashPassword(password);

  const result = await transaction(async (db) => {
    const existing = (await db.query(
      'SELECT id, email_verified FROM users WHERE email = $1 AND deleted_at IS NULL', [address],
    )).rows[0];
    if (existing?.email_verified) return { taken: true };
    let user;
    if (existing) {
      // Registered but never verified: let the real owner claim the address.
      user = (await db.query(
        `UPDATE users SET name = $2, password_hash = $3, phone = COALESCE($4, phone), language = COALESCE($5, language)
          WHERE id = $1 RETURNING ${USER_COLUMNS}`,
        [existing.id, name.trim(), passwordHash, phone ?? null, language ?? null],
      )).rows[0];
    } else {
      user = (await db.query(
        `INSERT INTO users (name, email, password_hash, phone, language, role)
         VALUES ($1, $2, $3, $4, COALESCE($5, 'en'), 'farmer') RETURNING ${USER_COLUMNS}`,
        [name.trim(), address, passwordHash, phone ?? null, language ?? null],
      )).rows[0];
    }
    const code = await issueCode(db, user, 'email_verification');
    return { user, code };
  }).catch((err) => {
    if (err.code === '23505' && err.constraint === 'uq_users_phone_active') {
      throw conflict('That phone number is already used by another account.');
    }
    throw err;
  });
  if (result.taken) throw fail(409, 'email_taken', 'An account with this email already exists. Please log in.');
  await sendCode(address, 'email_verification', result.code);
  return { email: address };
}

export async function verifyEmail({ email, code }) {
  const user = await one(`SELECT ${USER_COLUMNS} FROM users WHERE email = $1 AND deleted_at IS NULL`, [normaliseEmail(email)]);
  if (!user) throw fail(400, 'code_missing', 'No active code. Please ask for a new one.');
  if (user.email_verified) return { email: user.email, already: true };
  await consumeCode(user.id, 'email_verification', code);
  await query('UPDATE users SET email_verified = true WHERE id = $1', [user.id]);
  return { email: user.email };
}

export async function resendVerification({ email }) {
  const user = await one(
    `SELECT ${USER_COLUMNS} FROM users WHERE email = $1 AND deleted_at IS NULL AND NOT email_verified`,
    [normaliseEmail(email)],
  );
  if (user) {
    const code = await transaction((db) => issueCode(db, user, 'email_verification'));
    await sendCode(user.email, 'email_verification', code);
  }
}

export async function login({ email, password, remember, captcha_id, captcha_answer }, { userAgent, ip }) {
  const address = normaliseEmail(email);
  const user = await one(
    `SELECT ${USER_COLUMNS}, password_hash, failed_logins, locked_until
       FROM users WHERE email = $1 AND deleted_at IS NULL`,
    [address],
  );
  if (user?.locked_until && new Date(user.locked_until) > new Date()) {
    throw fail(429, 'account_locked', 'Too many wrong passwords. Please try again in a few minutes, or reset your password.');
  }
  if (user && user.failed_logins >= CAPTCHA_AFTER_FAILURES) {
    try {
      await checkCaptcha(captcha_id, captcha_answer);
    } catch (err) {
      err.details = { ...(err.details || {}), captcha_required: true };
      throw err;
    }
  }

  const ok = await verifyPassword(password, user?.password_hash);
  if (!ok) {
    if (user) {
      const { failed_logins: n } = await one(
        `UPDATE users SET failed_logins = failed_logins + 1,
                locked_until = CASE WHEN failed_logins + 1 >= $2
                                    THEN now() + $3 * interval '1 minute' END
          WHERE id = $1 RETURNING failed_logins`,
        [user.id, LOCK_AFTER_FAILURES, LOCK_MINUTES],
      );
      throw fail(401, 'invalid_credentials', 'Email or password is not right.',
        n >= CAPTCHA_AFTER_FAILURES ? { captcha_required: true } : undefined);
    }
    throw fail(401, 'invalid_credentials', 'Email or password is not right.');
  }
  if (!user.email_verified) {
    throw fail(403, 'email_unverified', 'Please verify your email first. We can send a new code.', { email: user.email });
  }

  return transaction(async (db) => {
    await db.query('UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = now() WHERE id = $1', [user.id]);
    const refresh = await issueRefreshToken(db, user, { persistent: Boolean(remember), userAgent, ip });
    return { user: publicUser(user), accessToken: signAccessToken(user), refresh };
  });
}

export async function forgotPassword({ email, captcha_id, captcha_answer }) {
  await checkCaptcha(captcha_id, captcha_answer);
  const user = await one(
    `SELECT ${USER_COLUMNS} FROM users WHERE email = $1 AND deleted_at IS NULL AND email_verified`,
    [normaliseEmail(email)],
  );
  if (user) {
    const code = await transaction((db) => issueCode(db, user, 'password_reset'));
    await sendCode(user.email, 'password_reset', code);
  }
}

/** Code -> a short-lived, single-use authorisation to set a new password. */
export async function verifyResetCode({ email, code }) {
  const user = await one('SELECT id FROM users WHERE email = $1 AND deleted_at IS NULL', [normaliseEmail(email)]);
  if (!user) throw fail(400, 'code_missing', 'No active code. Please ask for a new one.');
  await consumeCode(user.id, 'password_reset', code);
  const token = newOpaqueToken();
  await query(
    `INSERT INTO auth_challenges (id, kind, user_id, expires_at)
     VALUES ($1, 'password_reset', $2, now() + $3 * interval '1 minute')`,
    [sha256(token), user.id, RESET_AUTH_MINUTES],
  );
  return { reset_token: token, expires_in_s: RESET_AUTH_MINUTES * 60 };
}

export async function resetPassword({ reset_token, password }) {
  const problems = passwordProblems(password);
  if (problems.length) throw fail(422, 'weak_password', 'Choose a stronger password.', { problems });
  const passwordHash = await hashPassword(password);
  await transaction(async (db) => {
    const { rows } = await db.query(
      `DELETE FROM auth_challenges WHERE id = $1 AND kind = 'password_reset' AND expires_at > now()
       RETURNING user_id`,
      [sha256(String(reset_token || ''))],
    );
    if (!rows[0]) throw fail(400, 'reset_expired', 'This reset link has expired. Please start again.');
    await db.query(
      'UPDATE users SET password_hash = $2, failed_logins = 0, locked_until = NULL WHERE id = $1',
      [rows[0].user_id, passwordHash],
    );
    // Whoever knew the old password is logged out everywhere.
    await revokeEverything(db, rows[0].user_id);
  });
}

export async function changePassword(userId, { current_password, password }) {
  const user = await one('SELECT password_hash FROM users WHERE id = $1', [userId]);
  if (!(await verifyPassword(current_password, user?.password_hash))) {
    throw fail(401, 'invalid_credentials', 'Your current password is not right.');
  }
  const problems = passwordProblems(password);
  if (problems.length) throw fail(422, 'weak_password', 'Choose a stronger password.', { problems });
  const passwordHash = await hashPassword(password);
  await transaction(async (db) => {
    await db.query('UPDATE users SET password_hash = $2 WHERE id = $1', [userId, passwordHash]);
    await revokeEverything(db, userId);
  });
}

export async function setRole(userId, role) {
  if (!['farmer', 'agronomist', 'admin', 'super_admin'].includes(role)) throw badRequest('Unknown role.');
  return transaction(async (db) => {
    const { rows } = await db.query(
      `UPDATE users SET role = $2 WHERE id = $1 AND deleted_at IS NULL RETURNING ${USER_COLUMNS}`,
      [userId, role],
    );
    if (!rows[0]) return null;
    await revokeEverything(db, userId);      // the new role applies from the next login
    return publicUser(rows[0]);
  });
}

// Expired codes, captchas and refresh tokens: removed by the lifecycle job.
export async function purgeExpired() {
  const results = await Promise.all([
    query("DELETE FROM otp_verifications WHERE expires_at < now() - interval '1 day'"),
    query('DELETE FROM auth_challenges WHERE expires_at < now()'),
    query("DELETE FROM refresh_tokens WHERE expires_at < now() - interval '7 days'"),
  ]);
  return results.reduce((n, r) => n + r.rowCount, 0);
}

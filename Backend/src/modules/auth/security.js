/**
 * Cryptographic primitives for accounts. No I/O here: unit tested.
 *
 *  - Passwords: bcrypt(password + pepper). The pepper is only in the
 *    environment, so a stolen database alone cannot be brute-forced.
 *  - One-time codes and captcha answers: HMAC-SHA256 with the pepper, compared
 *    in constant time. Six digits from crypto.randomInt (uniform, unbiased).
 *  - Opaque tokens (refresh, captcha id, reset authorisation): 32 random bytes;
 *    only their SHA-256 is ever stored.
 */

import { createHash, createHmac, randomBytes, randomInt, timingSafeEqual } from 'node:crypto';

import bcrypt from 'bcrypt';

import { config } from '../../config/env.js';

// A real bcrypt hash of a random value, compared against when an account does
// not exist - so "no such user" and "wrong password" take the same time.
let dummyHash;

export async function hashPassword(password) {
  return bcrypt.hash(password + config.auth.passwordPepper, config.auth.bcryptRounds);
}

export async function verifyPassword(password, hash) {
  if (!hash) {
    dummyHash ??= await bcrypt.hash(randomBytes(16).toString('hex'), config.auth.bcryptRounds);
    await bcrypt.compare(password, dummyHash);
    return false;
  }
  return bcrypt.compare(password + config.auth.passwordPepper, hash);
}

export function hmac(value) {
  return createHmac('sha256', config.auth.passwordPepper).update(String(value)).digest('hex');
}

export function sha256(value) {
  return createHash('sha256').update(String(value)).digest('hex');
}

/** Constant-time comparison of two hex digests. */
export function sameHex(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  return timingSafeEqual(Buffer.from(a, 'hex'), Buffer.from(b, 'hex'));
}

export function newOtp() {
  return String(randomInt(100000, 1000000));
}

export function newOpaqueToken() {
  return randomBytes(32).toString('hex');
}

// ── validation rules shared by the routes and the forms ─────────────────────

export const EMAIL_PATTERN = '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$';

/** Problems with a new password, as short codes the app translates. [] = fine. */
export function passwordProblems(password) {
  const problems = [];
  if (typeof password !== 'string' || password.length < 8) problems.push('too_short');
  if (typeof password === 'string' && password.length > 128) problems.push('too_long');
  if (!/[a-z]/.test(password || '')) problems.push('needs_lowercase');
  if (!/[A-Z]/.test(password || '')) problems.push('needs_uppercase');
  if (!/[0-9]/.test(password || '')) problems.push('needs_number');
  if (!/[^A-Za-z0-9]/.test(password || '')) problems.push('needs_symbol');
  return problems;
}

export function normaliseEmail(email) {
  return String(email || '').trim().toLowerCase();
}

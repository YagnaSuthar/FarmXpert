const crypto = require('crypto');

/**
 * Shared crypto utilities.
 * Uses Node.js built-in crypto module for security-sensitive operations.
 *
 * NOTE: Feature-specific crypto (OTP generation, CAPTCHA) lives in
 * auth/auth.otp.js and auth/auth.captcha.js respectively.
 * This file contains only genuinely shared crypto helpers.
 */

/**
 * Generate a SHA-256 hash of a value.
 * Used for hashing OTPs and CAPTCHA answers before storage.
 * @param {string} value
 * @returns {string} hex-encoded hash
 */
function hashSHA256(value) {
  return crypto.createHash('sha256').update(String(value)).digest('hex');
}

/**
 * Generate cryptographically secure random bytes as a hex string.
 * @param {number} [length=32] Number of bytes
 * @returns {string} hex-encoded random string
 */
function generateSecureToken(length = 32) {
  return crypto.randomBytes(length).toString('hex');
}

/**
 * Constant-time string comparison to prevent timing attacks.
 * @param {string} a
 * @param {string} b
 * @returns {boolean}
 */
function timingSafeEqual(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  if (a.length !== b.length) return false;

  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  return crypto.timingSafeEqual(bufA, bufB);
}

module.exports = { hashSHA256, generateSecureToken, timingSafeEqual };

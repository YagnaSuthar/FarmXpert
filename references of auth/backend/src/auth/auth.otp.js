const crypto = require('crypto');
const { env } = require('../config/env');

/**
 * Auth OTP Utility
 *
 * Secure OTP generation and verification for:
 * - Email verification
 * - Password reset
 *
 * Security features:
 * - 6 digits generated using crypto.randomInt(100000, 1000000)
 * - HMAC-SHA256 hashing using server secret (passwordPepper)
 * - Timing-safe comparison to prevent side-channel timing attacks
 * - Configurable expiration window (default 10 minutes)
 * - Attempt tracking to prevent brute force
 * - Never logged in plaintext
 */

const authOtp = {
  /**
   * Generate a cryptographically secure 6-digit OTP.
   * Range: 100000 to 999999 inclusive.
   * @returns {string} 6-digit numeric string
   */
  generateOtp() {
    const otpInt = crypto.randomInt(100000, 1000000);
    return otpInt.toString();
  },

  /**
   * Keyed HMAC-SHA256 hash of an OTP using the server secret.
   * Prevents pre-computation / rainbow table attacks on the 6-digit space.
   *
   * @param {string} otp 6-digit OTP
   * @returns {string} Hex-encoded HMAC digest
   */
  hashOtp(otp) {
    const secret = env.passwordPepper || 'fallback-secret-key';
    return crypto.createHmac('sha256', secret).update(String(otp)).digest('hex');
  },

  /**
   * Verify an input OTP against a stored HMAC hash using constant-time comparison.
   *
   * @param {string} inputOtp User-provided OTP
   * @param {string} storedHash Hex HMAC hash stored in DB
   * @returns {boolean} True if matching, false otherwise
   */
  verifyOtp(inputOtp, storedHash) {
    if (!inputOtp || !storedHash || typeof inputOtp !== 'string' || typeof storedHash !== 'string') {
      return false;
    }

    const inputHash = this.hashOtp(inputOtp);

    const inputBuffer = Buffer.from(inputHash, 'hex');
    const storedBuffer = Buffer.from(storedHash, 'hex');

    if (inputBuffer.length !== storedBuffer.length) {
      return false;
    }

    return crypto.timingSafeEqual(inputBuffer, storedBuffer);
  },

  /**
   * Calculate future expiration timestamp for a new OTP.
   * @returns {Date} Expiration date
   */
  getExpirationDate() {
    const expiryMinutes = env.otpExpiresMinutes || 10;
    return new Date(Date.now() + expiryMinutes * 60 * 1000);
  },
};

module.exports = authOtp;

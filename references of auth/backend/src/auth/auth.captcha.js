const crypto = require('crypto');
const { env } = require('../config/env');

/**
 * Auth CAPTCHA
 *
 * Server-side CAPTCHA challenge generation and verification.
 *
 * Security:
 * - Generated on backend with cryptographically secure randomness (crypto.randomInt)
 * - 32-byte crypto random challenge ID
 * - Correct answer is NEVER sent to the client or logged
 * - Stored as a keyed HMAC-SHA256 hash using server secret
 * - Configurable expiration window (default 5 minutes)
 * - Strict attempt limits (default 3 attempts)
 * - Single-use enforcement (invalidated immediately upon successful verification)
 * - In-memory store with periodic automatic cleanup
 */

// In-memory challenge store (hackathon)
const captchaStore = new Map();

// Default limits
const MAX_CAPTCHA_ATTEMPTS = 3;

const authCaptcha = {
  /**
   * Keyed HMAC-SHA256 hash of the normalized answer.
   *
   * @param {string|number} answer
   * @returns {string} Hex HMAC digest
   */
  hashAnswer(answer) {
    const secret = env.passwordPepper || 'fallback-captcha-secret';
    const normalized = String(answer).trim().toLowerCase();
    return crypto.createHmac('sha256', secret).update(normalized).digest('hex');
  },

  /**
   * Generate a new CAPTCHA challenge.
   * Uses crypto.randomInt() to select operation and operands.
   *
   * @returns {{ captchaId: string, challenge: string, expiresAt: Date }} Public challenge (NO answer)
   */
  generateCaptcha() {
    const captchaId = crypto.randomBytes(32).toString('hex');
    const expiryMinutes = env.captchaExpiresMinutes || 5;
    const expiresAt = new Date(Date.now() + expiryMinutes * 60 * 1000);

    // Operations: 0: Addition, 1: Subtraction, 2: Multiplication
    const opType = crypto.randomInt(0, 3);
    let num1;
    let num2;
    let challenge;
    let answer;

    if (opType === 0) {
      num1 = crypto.randomInt(10, 50);
      num2 = crypto.randomInt(5, 30);
      challenge = `What is ${num1} + ${num2}?`;
      answer = num1 + num2;
    } else if (opType === 1) {
      num1 = crypto.randomInt(30, 80);
      num2 = crypto.randomInt(5, num1);
      challenge = `What is ${num1} - ${num2}?`;
      answer = num1 - num2;
    } else {
      num1 = crypto.randomInt(2, 10);
      num2 = crypto.randomInt(2, 10);
      challenge = `What is ${num1} * ${num2}?`;
      answer = num1 * num2;
    }

    // Store only the HMAC hash of the answer
    const answerHash = this.hashAnswer(answer);

    captchaStore.set(captchaId, {
      captchaId,
      answerHash,
      expiresAt,
      attempts: 0,
      maxAttempts: MAX_CAPTCHA_ATTEMPTS,
      used: false,
    });

    // Public challenge payload (answer is excluded)
    return {
      captchaId,
      challenge,
      expiresAt,
    };
  },

  /**
   * Verify an answer against a CAPTCHA challenge.
   *
   * Enforces:
   * - Challenge existence
   * - Expiration check
   * - Single-use enforcement
   * - Attempt counting and lockout
   * - Constant-time comparison
   *
   * @param {string} captchaId
   * @param {string|number} answer
   * @returns {{ isValid: boolean, error?: string }}
   */
  verifyCaptcha(captchaId, answer) {
    if (!captchaId || typeof captchaId !== 'string') {
      return { isValid: false, error: 'CAPTCHA ID is required' };
    }

    if (answer === undefined || answer === null || String(answer).trim() === '') {
      return { isValid: false, error: 'CAPTCHA answer is required' };
    }

    const record = captchaStore.get(captchaId);
    if (!record) {
      return { isValid: false, error: 'Invalid or expired CAPTCHA challenge. Please request a new one.' };
    }

    // Single-use check
    if (record.used) {
      captchaStore.delete(captchaId);
      return { isValid: false, error: 'CAPTCHA challenge has already been used. Please request a new one.' };
    }

    // Expiration check
    if (new Date() > new Date(record.expiresAt)) {
      captchaStore.delete(captchaId);
      return { isValid: false, error: 'CAPTCHA challenge has expired. Please request a new one.' };
    }

    // Attempt limit check
    if (record.attempts >= record.maxAttempts) {
      captchaStore.delete(captchaId);
      return { isValid: false, error: 'Maximum CAPTCHA attempts exceeded. Please request a new CAPTCHA.' };
    }

    const inputHash = this.hashAnswer(answer);
    const inputBuffer = Buffer.from(inputHash, 'hex');
    const storedBuffer = Buffer.from(record.answerHash, 'hex');

    const isMatch = inputBuffer.length === storedBuffer.length &&
      crypto.timingSafeEqual(inputBuffer, storedBuffer);

    if (!isMatch) {
      record.attempts += 1;
      const remaining = record.maxAttempts - record.attempts;

      if (record.attempts >= record.maxAttempts) {
        captchaStore.delete(captchaId);
        return { isValid: false, error: 'Incorrect CAPTCHA answer. Maximum attempts reached.' };
      }

      return {
        isValid: false,
        error: `Incorrect CAPTCHA answer. ${remaining} attempt(s) remaining.`,
      };
    }

    // Success: invalidate challenge immediately (single-use)
    record.used = true;
    captchaStore.delete(captchaId);

    return { isValid: true };
  },

  /**
   * In-memory store cleanup for expired challenges.
   * @returns {number} Removed count
   */
  cleanExpiredCaptchas() {
    const now = new Date();
    let count = 0;
    for (const [id, record] of captchaStore.entries()) {
      if (now > new Date(record.expiresAt) || record.used) {
        captchaStore.delete(id);
        count++;
      }
    }
    return count;
  },

  /**
   * Get count of active challenges in memory (for testing).
   */
  getStoreSize() {
    return captchaStore.size;
  },
};

// Periodic background cleanup every 10 minutes
setInterval(() => {
  authCaptcha.cleanExpiredCaptchas();
}, 10 * 60 * 1000).unref();

module.exports = authCaptcha;

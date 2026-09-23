const dotenv = require('dotenv');
const path = require('path');

// Load .env from project root (Backend/)
dotenv.config({ path: path.resolve(__dirname, '../../.env') });

/**
 * Validated environment configuration.
 * Fails fast if critical variables are missing.
 */
const env = {
  // Server
  nodeEnv: process.env.NODE_ENV || 'development',
  port: parseInt(process.env.PORT, 10) || 5000,
  isProduction: process.env.NODE_ENV === 'production',

  // PostgreSQL
  db: {
    host: process.env.DB_HOST || 'localhost',
    port: parseInt(process.env.DB_PORT, 10) || 5432,
    name: process.env.DB_NAME || 'ODOO_INDIA',
    user: process.env.DB_USER || 'postgres',
    password: process.env.DB_PASSWORD,
  },

  // Security — Passwords
  bcryptRounds: parseInt(process.env.BCRYPT_ROUNDS, 10) || 12,
  passwordPepper: process.env.PASSWORD_PEPPER,

  // Security — JWT
  jwtSecret: process.env.JWT_SECRET,
  jwtExpiresIn: process.env.JWT_EXPIRES_IN || '15m',

  // Security — Sessions
  sessionSecret: process.env.SESSION_SECRET,
  sessionMaxAgeMs: parseInt(process.env.SESSION_MAX_AGE_MS, 10) || 1800000,

  // Email
  smtp: {
    host: process.env.SMTP_HOST || 'smtp.gmail.com',
    port: parseInt(process.env.SMTP_PORT, 10) || 587,
    user: process.env.SMTP_USER,
    pass: process.env.SMTP_PASS,
    fromName: process.env.SMTP_FROM_NAME || 'Management Software',
  },

  // CORS
  corsOrigin: process.env.CORS_ORIGIN || 'http://localhost:3000',

  // Rate Limiting
  rateLimitWindowMs: parseInt(process.env.RATE_LIMIT_WINDOW_MS, 10) || 900000,
  rateLimitMax: parseInt(process.env.RATE_LIMIT_MAX, 10) || 100,
  authRateLimitWindowMs: parseInt(process.env.AUTH_RATE_LIMIT_WINDOW_MS, 10) || 900000,
  authRateLimitMax: parseInt(process.env.AUTH_RATE_LIMIT_MAX, 10) || 100,

  // OTP
  otpExpiresMinutes: parseInt(process.env.OTP_EXPIRES_MINUTES, 10) || 10,
  otpMaxAttempts: parseInt(process.env.OTP_MAX_ATTEMPTS, 10) || 5,

  // CAPTCHA
  captchaExpiresMinutes: parseInt(process.env.CAPTCHA_EXPIRES_MINUTES, 10) || 5,

  // Refresh Token (Remember Me)
  refreshTokenExpiresDays: parseInt(process.env.REFRESH_TOKEN_EXPIRES_DAYS, 10) || 30,
};

/**
 * Validate that critical environment variables are present.
 * Logs warnings for non-critical missing vars in development.
 */
function validateEnv() {
  const critical = [];
  const warnings = [];

  if (!env.db.password) critical.push('DB_PASSWORD');
  if (!env.passwordPepper) critical.push('PASSWORD_PEPPER');
  if (!env.jwtSecret) critical.push('JWT_SECRET');
  if (!env.sessionSecret) critical.push('SESSION_SECRET');

  if (!env.smtp.user) warnings.push('SMTP_USER');
  if (!env.smtp.pass) warnings.push('SMTP_PASS');

  if (critical.length > 0) {
    console.error(`[ENV] FATAL: Missing critical environment variables: ${critical.join(', ')}`);
    console.error('[ENV] Please check your .env file.');
    process.exit(1);
  }

  if (warnings.length > 0 && !env.isProduction) {
    console.warn(`[ENV] Warning: Missing optional environment variables: ${warnings.join(', ')}`);
    console.warn('[ENV] Email functionality will not work until these are configured.');
  }
}

module.exports = { env, validateEnv };

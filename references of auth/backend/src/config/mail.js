const nodemailer = require('nodemailer');
const { env } = require('./env');

/**
 * Nodemailer transporter configured for Gmail SMTP.
 *
 * Requires a Gmail App Password (not your regular password).
 * Generate one at: https://myaccount.google.com/apppasswords
 *
 * This transporter is created once and reused across the application.
 * The auth.email.js module wraps this for feature-specific email sending.
 */
const transporter = nodemailer.createTransport({
  host: env.smtp.host,
  port: env.smtp.port,
  secure: false, // true for 465, false for other ports (STARTTLS)
  auth: {
    user: env.smtp.user,
    pass: env.smtp.pass,
  },
});

/**
 * Verify the SMTP connection is working.
 * @returns {Promise<boolean>}
 */
async function verifyMailConnection() {
  try {
    if (!env.smtp.user || !env.smtp.pass) {
      console.warn('[MAIL] SMTP credentials not configured — email disabled');
      return false;
    }
    await transporter.verify();
    console.log('[MAIL] SMTP connection verified successfully');
    return true;
  } catch (err) {
    console.warn('[MAIL] SMTP connection failed:', err.message);
    console.warn('[MAIL] Email functionality will not work until SMTP is configured.');
    return false;
  }
}

module.exports = { transporter, verifyMailConnection };

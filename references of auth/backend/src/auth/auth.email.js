const { transporter } = require('../config/mail');
const { env } = require('../config/env');
const logger = require('../utils/logger');

/**
 * Auth Email
 *
 * Feature-specific email sending for authentication flows.
 * Wraps the shared Nodemailer transporter from config/mail.js.
 *
 * Emails sent:
 * - Email verification OTP
 * - Password reset OTP
 *
 * SECURITY:
 * - Never logs plaintext OTP values
 * - Never includes OTP in response bodies
 * - Handles email dispatch asynchronously and gracefully
 */

const authEmail = {
  /**
   * Send email verification OTP to user.
   *
   * @param {string} to Recipient email address
   * @param {string} otp 6-digit verification code
   * @returns {Promise<boolean>} True if sent or bypassed in dev, false on failure
   */
  async sendVerificationEmail(to, otp) {
    if (!env.smtp.user || !env.smtp.pass || env.smtp.pass === 'your-gmail-app-password') {
      logger.warn('SMTP credentials not configured. Skipping email dispatch.', {
        recipient: to,
      });
      return false;
    }

    const mailOptions = {
      from: `"${env.smtp.fromName}" <${env.smtp.user}>`,
      to,
      subject: 'Verify Your Email Address',
      text: `Welcome! Your 6-digit email verification code is: ${otp}\n\nThis code will expire in ${env.otpExpiresMinutes} minutes. If you did not request this, please ignore this email.`,
      html: `
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
          <h2 style="color: #333333; text-align: center;">Verify Your Email Address</h2>
          <p style="color: #555555; font-size: 15px;">Thank you for registering. Please use the verification code below to verify your email address:</p>
          <div style="text-align: center; margin: 30px 0;">
            <span style="display: inline-block; font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #1a73e8; background: #f1f3f4; padding: 12px 24px; border-radius: 6px;">
              ${otp}
            </span>
          </div>
          <p style="color: #777777; font-size: 13px;">This code will expire in <strong>${env.otpExpiresMinutes} minutes</strong>.</p>
          <p style="color: #999999; font-size: 12px; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px;">
            If you did not create an account, please ignore this message.
          </p>
        </div>
      `,
    };

    try {
      await transporter.sendMail(mailOptions);
      logger.info('Verification email dispatched', { recipient: to });
      return true;
    } catch (err) {
      logger.error('Failed to send verification email', {
        recipient: to,
        error: err.message,
      });
      return false;
    }
  },

  /**
   * Send password reset OTP to user.
   *
   * @param {string} to Recipient email address
   * @param {string} otp 6-digit password reset code
   * @returns {Promise<boolean>}
   */
  async sendPasswordResetEmail(to, otp) {
    if (!env.smtp.user || !env.smtp.pass || env.smtp.pass === 'your-gmail-app-password') {
      logger.warn('SMTP credentials not configured. Skipping email dispatch.', {
        recipient: to,
      });
      return false;
    }

    const mailOptions = {
      from: `"${env.smtp.fromName}" <${env.smtp.user}>`,
      to,
      subject: 'Password Reset Request',
      text: `You requested a password reset. Your 6-digit verification code is: ${otp}\n\nThis code will expire in ${env.otpExpiresMinutes} minutes. If you did not request this, your account is safe and you can ignore this email.`,
      html: `
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
          <h2 style="color: #d93025; text-align: center;">Password Reset Request</h2>
          <p style="color: #555555; font-size: 15px;">We received a request to reset your password. Use the verification code below to authorize the reset:</p>
          <div style="text-align: center; margin: 30px 0;">
            <span style="display: inline-block; font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #d93025; background: #fce8e6; padding: 12px 24px; border-radius: 6px;">
              ${otp}
            </span>
          </div>
          <p style="color: #777777; font-size: 13px;">This code is valid for <strong>${env.otpExpiresMinutes} minutes</strong> and can only be used once.</p>
          <p style="color: #999999; font-size: 12px; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px;">
            If you did not request a password reset, please ignore this email or contact support if you suspect unauthorized activity.
          </p>
        </div>
      `,
    };

    try {
      await transporter.sendMail(mailOptions);
      logger.info('Password reset email dispatched', { recipient: to });
      return true;
    } catch (err) {
      logger.error('Failed to send password reset email', {
        recipient: to,
        error: err.message,
      });
      return false;
    }
  },
};

module.exports = authEmail;

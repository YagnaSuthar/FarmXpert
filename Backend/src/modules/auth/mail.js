/**
 * Account emails: verification and password-reset codes.
 *
 * Without SMTP configured (local development) the code is written to the log
 * instead, so the whole flow can be exercised without a mail server.
 * Production refuses to start without SMTP_HOST.
 */

import nodemailer from 'nodemailer';

import { config } from '../../config/env.js';
import { logger } from '../../lib/logger.js';

let transporter = null;

function transport() {
  if (!config.smtp.host) return null;
  transporter ??= nodemailer.createTransport({
    host: config.smtp.host,
    port: config.smtp.port,
    secure: config.smtp.port === 465,
    auth: config.smtp.user ? { user: config.smtp.user, pass: config.smtp.pass } : undefined,
    pool: true,
    maxConnections: 3,
  });
  return transporter;
}

const COPY = {
  email_verification: {
    subject: 'Your FarmXpert verification code',
    title: 'Welcome to FarmXpert',
    line: 'Use this code to verify your email address.',
  },
  password_reset: {
    subject: 'Your FarmXpert password reset code',
    title: 'Reset your password',
    line: 'Use this code to set a new password. If you did not ask for this, you can ignore this email - your account is safe.',
  },
};

function html(copy, code) {
  // Brand colours inline: most mail clients drop <style>.
  return `<div style="background:#fbf7f1;padding:32px 12px;font-family:Arial,Helvetica,sans-serif">
  <div style="max-width:480px;margin:0 auto;background:#ffffff;border:1px solid #e9e1d4;border-radius:20px;overflow:hidden">
    <div style="background:#0f4a2e;padding:24px 28px;color:#ffffff">
      <div style="font-size:12px;letter-spacing:3px;color:#b8913a">FARMXPERT</div>
      <div style="font-size:22px;margin-top:6px;font-family:Georgia,serif">${copy.title}</div>
    </div>
    <div style="padding:28px">
      <p style="color:#1d2b22;font-size:15px;line-height:1.6;margin:0 0 20px">${copy.line}</p>
      <div style="text-align:center;margin:24px 0">
        <span style="display:inline-block;font-size:32px;font-weight:bold;letter-spacing:8px;color:#0f4a2e;background:#e8f1e1;padding:14px 26px;border-radius:14px">${code}</span>
      </div>
      <p style="color:#5f6b62;font-size:13px;margin:0">This code expires in ${config.auth.otpMinutes} minutes and works once.</p>
    </div>
  </div>
</div>`;
}

export async function sendCode(to, purpose, code) {
  const copy = COPY[purpose];
  const mailer = transport();
  if (!mailer) {
    // Development only (production requires SMTP). Never log codes in production.
    logger.warn({ to, purpose, code }, 'SMTP not configured - verification code logged instead of emailed');
    return false;
  }
  try {
    await mailer.sendMail({
      from: `"${config.smtp.fromName}" <${config.smtp.fromEmail}>`,
      to,
      subject: copy.subject,
      text: `${copy.title}\n\n${copy.line}\n\nCode: ${code}\n\nIt expires in ${config.auth.otpMinutes} minutes.`,
      html: html(copy, code),
    });
    return true;
  } catch (err) {
    // The user can ask for a new code; a mail outage must not crash the request.
    logger.error({ err: err.message, purpose }, 'Sending the code email failed');
    return false;
  }
}

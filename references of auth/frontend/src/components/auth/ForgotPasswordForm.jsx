'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';
import api from '@/lib/api';

export default function ForgotPasswordForm({ onSwitchToLogin, onProceedToVerify }) {
  const t = useTranslations('auth');
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSent, setIsSent] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [backendMessage, setBackendMessage] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');

    if (!email.trim()) {
      setErrorMessage(t('register.emailLabel') + ' is required');
      return;
    }

    setIsSubmitting(true);

    try {
      const res = await api.post('/auth/forgot-password', {
        email: email.trim().toLowerCase(),
      });

      // Always show generic message to prevent account enumeration
      setBackendMessage(res.message || t('forgotPassword.successMessage'));
      setIsSent(true);
    } catch (err) {
      // Even if network or validation error, display user-friendly message
      setErrorMessage(err.message || t('errors.generic'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResend = async () => {
    if (email.trim()) {
      setIsSubmitting(true);
      try {
        const res = await api.post('/auth/forgot-password', {
          email: email.trim().toLowerCase(),
        });
        setBackendMessage(res.message || t('forgotPassword.successMessage'));
      } catch {
        // Keep generic
      } finally {
        setIsSubmitting(false);
      }
    }
  };

  return (
    <>
      <header className="form-head-auth">
        <h1 className="form-title-auth">{t('forgotPassword.title')}</h1>
        <p className="form-sub-auth">{t('forgotPassword.subtitle')}</p>
      </header>

      {/* Error Message Banner */}
      {errorMessage && (
        <div className="error-banner-auth" role="alert">
          <svg
            className="error-icon-auth"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <div>
            <p className="error-title-auth">{errorMessage}</p>
          </div>
        </div>
      )}

      {isSent ? (
        <div className="login-form-auth">
          <div className="status-banner-auth">
            <svg
              className="status-icon-auth"
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            <div>
              <h3 className="status-title-auth">{t('forgotPassword.successTitle')}</h3>
              <p className="status-desc-auth">{backendMessage || t('forgotPassword.successMessage')}</p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', marginTop: '0.5rem' }}>
            {onProceedToVerify ? (
              <button
                type="button"
                onClick={() => onProceedToVerify(email.trim().toLowerCase())}
                className="btn-primary-auth btn-full-width-auth"
              >
                <span>{t('verifyResetOtp.submitButton')}</span>
              </button>
            ) : (
              <Link href="/auth/reset-password" className="btn-primary-auth btn-full-width-auth">
                <span>{t('verifyResetOtp.submitButton')}</span>
              </Link>
            )}

            <div className="otp-actions-auth" style={{ justifyContent: 'center', marginTop: '0.6rem' }}>
              <span>{t('forgotPassword.resendPrompt')}</span>
              <button
                type="button"
                className="btn-link-auth"
                onClick={handleResend}
                disabled={isSubmitting}
              >
                {t('forgotPassword.resendAction')}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <form className="login-form-auth" onSubmit={handleSubmit} noValidate>
          <div className="field-auth">
            <label className="field-label-auth" htmlFor="forgot-email">
              {t('forgotPassword.emailLabel')}
            </label>
            <input
              id="forgot-email"
              name="email"
              type="email"
              autoComplete="email"
              placeholder={t('forgotPassword.emailPlaceholder')}
              className="field-input-auth"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={isSubmitting}
            />
          </div>

          <button
            type="submit"
            className="btn-primary-auth"
            disabled={isSubmitting}
            style={{ marginTop: '1rem' }}
          >
            <span>
              {isSubmitting
                ? t('forgotPassword.submittingButton')
                : t('forgotPassword.submitButton')}
            </span>
          </button>
        </form>
      )}

      <div className="back-link-wrap-auth">
        {onSwitchToLogin ? (
          <button
            type="button"
            onClick={onSwitchToLogin}
            className="nav-back-auth btn-link-auth"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            <span>{t('forgotPassword.backToLogin')}</span>
          </button>
        ) : (
          <Link href="/auth/login" className="nav-back-auth">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            <span>{t('forgotPassword.backToLogin')}</span>
          </Link>
        )}
      </div>
    </>
  );
}

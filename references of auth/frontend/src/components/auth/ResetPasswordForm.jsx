'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Link, useRouter } from '@/i18n/navigation';
import api from '@/lib/api';

export default function ResetPasswordForm({
  resetToken = '',
  onSwitchToLogin,
  onSwitchToForgot,
}) {
  const t = useTranslations('auth');
  const router = useRouter();

  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [errorList, setErrorList] = useState([]);
  const [formData, setFormData] = useState({
    token: resetToken,
    newPassword: '',
    confirmPassword: '',
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorList([]);

    const tokenToUse = formData.token || resetToken;
    if (!tokenToUse) {
      setErrorList(['Reset authorization token missing. Please request a new password reset code.']);
      return;
    }

    if (!formData.newPassword) {
      setErrorList(['Please enter a new password']);
      return;
    }

    if (formData.newPassword !== formData.confirmPassword) {
      setErrorList([t('errors.passwordsDoNotMatch')]);
      return;
    }

    setIsSubmitting(true);

    try {
      const res = await api.post('/auth/reset-password', {
        resetToken: tokenToUse.trim(),
        newPassword: formData.newPassword,
      });

      if (res.success) {
        setIsSuccess(true);
        setTimeout(() => {
          if (onSwitchToLogin) {
            onSwitchToLogin();
          } else {
            router.push('/auth/login');
          }
        }, 1500);
      }
    } catch (err) {
      if (err.errors && Array.isArray(err.errors) && err.errors.length > 0) {
        setErrorList(err.errors);
      } else {
        setErrorList([err.message || t('errors.generic')]);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <header className="form-head-auth">
        <h1 className="form-title-auth">{t('resetPassword.title')}</h1>
        <p className="form-sub-auth">{t('resetPassword.subtitle')}</p>
      </header>

      {/* Error Message Banner */}
      {errorList.length > 0 && (
        <div className="error-banner-auth" role="alert">
          <svg
            className="error-icon-auth"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <div className="error-content-auth">
            {errorList.length === 1 ? (
              <p className="error-title-auth">{errorList[0]}</p>
            ) : (
              <ul className="error-list-auth">
                {errorList.map((err, idx) => (
                  <li key={idx} className="error-list-item-auth">
                    {err}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {isSuccess ? (
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
            >
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            <div>
              <h3 className="status-title-auth">{t('resetPassword.title')}</h3>
              <p className="status-desc-auth">Password updated successfully! Redirecting to login...</p>
            </div>
          </div>
        </div>
      ) : (
        <form className="login-form-auth" onSubmit={handleSubmit} noValidate>
          {/* New Password */}
          <div className="field-auth">
            <label className="field-label-auth" htmlFor="new-password">
              {t('resetPassword.newPasswordLabel')}
            </label>
            <div className="field-control-auth">
              <input
                id="new-password"
                name="newPassword"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder={t('resetPassword.newPasswordPlaceholder')}
                className="field-input-auth"
                value={formData.newPassword}
                onChange={(e) => setFormData({ ...formData, newPassword: e.target.value })}
                required
                disabled={isSubmitting}
              />
              <button
                type="button"
                className="peek-btn-auth"
                onClick={() => setShowPassword((prev) => !prev)}
                aria-label={showPassword ? t('common.hidePassword') : t('common.showPassword')}
                aria-pressed={showPassword}
                tabIndex={-1}
              >
                {showPassword ? (
                  <svg className="peek-eye-auth" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                    <path
                      d="M3 3l14 14M9.5 9.5a2.5 2.5 0 003.5 3.5m-1.5-6.5C14 6.5 17 9.5 17 9.5s-1.2 2.3-3.2 4.1M7.5 7.8C4.5 9.2 3 10 3 10s3 6 7 6c1.5 0 2.9-.5 4.1-1.3"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  <svg className="peek-eye-auth" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                    <path
                      d="M1 10s3.2-6 9-6 9 6 9 6-3.2 6-9 6-9-6-9-6Z"
                      stroke="currentColor"
                      strokeWidth="1.4"
                      strokeLinejoin="round"
                    />
                    <circle cx="10" cy="10" r="2.4" stroke="currentColor" strokeWidth="1.4" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          {/* Confirm New Password */}
          <div className="field-auth">
            <label className="field-label-auth" htmlFor="confirm-new-password">
              {t('resetPassword.confirmPasswordLabel')}
            </label>
            <input
              id="confirm-new-password"
              name="confirmPassword"
              type={showPassword ? 'text' : 'password'}
              autoComplete="new-password"
              placeholder={t('resetPassword.confirmPasswordPlaceholder')}
              className="field-input-auth"
              value={formData.confirmPassword}
              onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
              required
              disabled={isSubmitting}
            />
          </div>

          <button
            type="submit"
            className="btn-primary-auth btn-full-width-auth"
            disabled={isSubmitting}
            style={{ marginTop: '0.8rem' }}
          >
            <span>
              {isSubmitting
                ? t('resetPassword.submittingButton')
                : t('resetPassword.submitButton')}
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
            <span>{t('resetPassword.backToLogin')}</span>
          </button>
        ) : (
          <Link href="/auth/login" className="nav-back-auth">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            <span>{t('resetPassword.backToLogin')}</span>
          </Link>
        )}
      </div>
    </>
  );
}

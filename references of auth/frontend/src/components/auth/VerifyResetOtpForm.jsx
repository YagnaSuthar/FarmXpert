'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';
import api from '@/lib/api';

export default function VerifyResetOtpForm({
  email: initialEmail = '',
  onSwitchToLogin,
  onSuccess,
}) {
  const t = useTranslations('auth');

  const [email, setEmail] = useState(initialEmail);
  const [digits, setDigits] = useState(['', '', '', '', '', '']);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [countdown, setCountdown] = useState(59);
  const [errorMessage, setErrorMessage] = useState('');
  const [infoMessage, setInfoMessage] = useState('');
  const inputsRef = useRef([]);

  const effectiveEmail = email || initialEmail;

  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  const handleDigitChange = (index, value) => {
    const char = value.replace(/\D/g, '').slice(-1);
    const newDigits = [...digits];
    newDigits[index] = char;
    setDigits(newDigits);

    if (char && index < 5) {
      inputsRef.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      inputsRef.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pasteData = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    if (!pasteData) return;

    const newDigits = [...digits];
    for (let i = 0; i < pasteData.length; i++) {
      newDigits[i] = pasteData[i];
    }
    setDigits(newDigits);

    const nextIndex = Math.min(pasteData.length, 5);
    inputsRef.current[nextIndex]?.focus();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setInfoMessage('');

    const otpCode = digits.join('');
    if (otpCode.length !== 6) {
      return;
    }

    if (!email.trim()) {
      setErrorMessage(t('register.emailLabel') + ' is required');
      return;
    }

    setIsSubmitting(true);

    try {
      const res = await api.post('/auth/verify-reset-otp', {
        email: email.trim().toLowerCase(),
        otp: otpCode,
      });

      if (res.success && res.data?.resetToken) {
        if (onSuccess) {
          onSuccess(res.data.resetToken);
        }
      }
    } catch (err) {
      setErrorMessage(err.message || t('errors.generic'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResend = async () => {
    if (countdown === 0 && email.trim()) {
      setErrorMessage('');
      setInfoMessage('');
      try {
        const res = await api.post('/auth/forgot-password', {
          email: email.trim().toLowerCase(),
        });
        setInfoMessage(res.message || 'Reset code resent');
        setCountdown(59);
        setDigits(['', '', '', '', '', '']);
        inputsRef.current[0]?.focus();
      } catch (err) {
        setErrorMessage(err.message || t('errors.generic'));
      }
    }
  };

  const isCodeComplete = digits.every((d) => d !== '');

  return (
    <>
      <header className="form-head-auth">
        <h1 className="form-title-auth">{t('verifyResetOtp.title')}</h1>
        <p className="form-sub-auth">
          {email ? (
            <>
              {t('verifyResetOtp.subtitle')} (<strong>{email}</strong>)
            </>
          ) : (
            t('verifyResetOtp.subtitle')
          )}
        </p>
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

      {/* Info / Notice Banner */}
      {infoMessage && (
        <div className="status-banner-auth">
          <svg
            className="status-icon-auth"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <div>
            <p className="status-desc-auth">{infoMessage}</p>
          </div>
        </div>
      )}

      <form className="login-form-auth" onSubmit={handleSubmit} noValidate>
        {!initialEmail && (
          <div className="field-auth">
            <label className="field-label-auth" htmlFor="reset-email-input">
              {t('register.emailLabel')}
            </label>
            <input
              id="reset-email-input"
              name="email"
              type="email"
              placeholder={t('register.emailPlaceholder')}
              className="field-input-auth"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={isSubmitting}
            />
          </div>
        )}

        <div className="field-auth">
          <label className="field-label-auth">{t('verifyResetOtp.codeLabel')}</label>
          <div className="otp-inputs-auth" onPaste={handlePaste}>
            {digits.map((digit, idx) => (
              <input
                key={idx}
                ref={(el) => (inputsRef.current[idx] = el)}
                type="text"
                inputMode="numeric"
                maxLength={1}
                pattern="[0-9]*"
                className="otp-digit-auth"
                value={digit}
                onChange={(e) => handleDigitChange(idx, e.target.value)}
                onKeyDown={(e) => handleKeyDown(idx, e)}
                aria-label={`Digit ${idx + 1}`}
                autoFocus={idx === 0}
                disabled={isSubmitting}
              />
            ))}
          </div>
        </div>

        <button
          type="submit"
          className="btn-primary-auth btn-full-width-auth"
          disabled={!isCodeComplete || isSubmitting}
        >
          <span>
            {isSubmitting
              ? t('verifyResetOtp.submittingButton')
              : t('verifyResetOtp.submitButton')}
          </span>
        </button>

        {/* Resend prompt below verify button aligned to the right side */}
        <div className="otp-actions-auth otp-resend-row-auth">
          <span className="otp-resend-prompt-auth">
            {countdown > 0
              ? t('verifyResetOtp.resendCountdown', { seconds: countdown })
              : "Didn't receive the email?"}
          </span>
          {countdown === 0 && (
            <button
              type="button"
              className="btn-link-auth otp-resend-btn-auth"
              disabled={isSubmitting}
              onClick={handleResend}
            >
              {t('verifyResetOtp.resendButton')}
            </button>
          )}
        </div>
      </form>

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
            <span>{t('verifyResetOtp.backToLogin')}</span>
          </button>
        ) : (
          <Link href="/auth/login" className="nav-back-auth">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            <span>{t('verifyResetOtp.backToLogin')}</span>
          </Link>
        )}
      </div>
    </>
  );
}

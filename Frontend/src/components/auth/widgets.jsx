'use client';

// ============================================================
// FILE: src/components/auth/widgets.jsx
// Pieces of the auth forms, in the reference's '-auth' vocabulary:
// fields, the password peek, OTP digits, strength meter, CAPTCHA,
// banners, and the submit pill.
// ============================================================

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertCircle, Check, CheckCircle2, Loader2, RefreshCw } from '@/components/ui/icons';

import { api } from '@/lib/api';

export function Field({ label, hint, error, optional, children }) {
  const id = useId();
  return (
    <div className="field-auth">
      <label className="field-label-auth" htmlFor={id}>
        {label}{optional && <span>{optional}</span>}
      </label>
      {children({ id, 'aria-invalid': error ? 'true' : undefined, 'aria-describedby': error ? `${id}-e` : undefined })}
      {error ? <p id={`${id}-e`} className="field-error-auth">{error}</p>
        : hint ? <p className="field-error-auth" style={{ color: 'var(--auth-text-3)' }}>{hint}</p> : null}
    </div>
  );
}

export function Input({ label, error, optional, hint, ...props }) {
  return (
    <Field label={label} error={error} optional={optional} hint={hint}>
      {(a) => <input className="field-input-auth" {...a} {...props} />}
    </Field>
  );
}

const EyeOpen = () => (
  <svg className="peek-eye-auth" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M1 10s3.2-6 9-6 9 6 9 6-3.2 6-9 6-9-6-9-6Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    <circle cx="10" cy="10" r="2.4" stroke="currentColor" strokeWidth="1.4" />
  </svg>
);
const EyeShut = () => (
  <svg className="peek-eye-auth" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 3l14 14M9.5 9.5a2.5 2.5 0 003.5 3.5m-1.5-6.5C14 6.5 17 9.5 17 9.5s-1.2 2.3-3.2 4.1M7.5 7.8C4.5 9.2 3 10 3 10s3 6 7 6c1.5 0 2.9-.5 4.1-1.3"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export function PasswordInput({ label, error, showLabel, hideLabel, ...props }) {
  const [visible, setVisible] = useState(false);
  return (
    <Field label={label} error={error}>
      {(a) => (
        <div className="field-control-auth">
          <input className="field-input-auth" {...a} {...props} type={visible ? 'text' : 'password'} />
          <button type="button" className="peek-btn-auth" onClick={() => setVisible((v) => !v)}
            aria-label={visible ? hideLabel : showLabel} aria-pressed={visible}>
            {visible ? <EyeShut /> : <EyeOpen />}
          </button>
        </div>
      )}
    </Field>
  );
}

export function Checkbox({ checked, onChange, children, top = false, invalid }) {
  return (
    <label className={`checkbox-auth${top ? ' top-auth' : ''}`}>
      <input type="checkbox" className="checkbox-input-auth" checked={checked} onChange={(e) => onChange(e.target.checked)}
        aria-invalid={invalid ? 'true' : undefined} />
      <span className="checkbox-box-auth" aria-hidden="true">
        <svg className="checkbox-check-auth" viewBox="0 0 10 8" fill="none">
          <path d="M1 4l2.6 2.6L9 1" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span>{children}</span>
    </label>
  );
}

export function Banner({ tone = 'error', children }) {
  if (!children) return null;
  const Icon = tone === 'error' ? AlertCircle : CheckCircle2;
  return (
    <div className={tone === 'error' ? 'error-banner-auth' : 'success-banner-auth'} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon className="banner-icon-auth" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function Submit({ busy, children, disabled, onClick, type = 'submit' }) {
  return (
    <button type={type} className="btn-primary-auth" disabled={busy || disabled} onClick={onClick} aria-busy={busy || undefined}>
      {busy && <Loader2 className="spin-auth" aria-hidden />}
      {children}
    </button>
  );
}

/** Six digits. Typing moves on, Backspace goes back, a pasted code fills them all. */
export function OtpInput({ value, onChange, disabled, invalid, label }) {
  const refs = useRef([]);
  const digits = Array.from({ length: 6 }, (_, i) => value[i] || '');
  const setAt = (i, d) => {
    const next = digits.slice();
    next[i] = d;
    onChange(next.join('').slice(0, 6));
  };
  return (
    <div className="otp-inputs-auth" role="group" aria-label={label} onPaste={(e) => {
      const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
      if (!pasted) return;
      e.preventDefault();
      onChange(pasted);
      refs.current[Math.min(pasted.length, 5)]?.focus();
    }}>
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => { refs.current[i] = el; }}
          className={`otp-digit-auth${d ? ' filled-auth' : ''}`}
          value={d}
          inputMode="numeric"
          autoComplete={i === 0 ? 'one-time-code' : 'off'}
          maxLength={6}
          disabled={disabled}
          autoFocus={i === 0}
          aria-label={`${label} ${i + 1}`}
          aria-invalid={invalid ? 'true' : undefined}
          onFocus={(e) => e.target.select()}
          onKeyDown={(e) => {
            if (e.key === 'Backspace' && !digits[i] && i > 0) { refs.current[i - 1]?.focus(); setAt(i - 1, ''); }
            if (e.key === 'ArrowLeft' && i > 0) refs.current[i - 1]?.focus();
            if (e.key === 'ArrowRight' && i < 5) refs.current[i + 1]?.focus();
          }}
          onChange={(e) => {
            const typed = e.target.value.replace(/\D/g, '');
            if (!typed) return setAt(i, '');
            if (typed.length > 1) {
              const next = (digits.slice(0, i).join('') + typed).slice(0, 6);
              onChange(next);
              refs.current[Math.min(next.length, 5)]?.focus();
              return undefined;
            }
            setAt(i, typed);
            if (i < 5) refs.current[i + 1]?.focus();
            return undefined;
          }}
        />
      ))}
    </div>
  );
}

// The server's rules (Backend auth/security.js passwordProblems).
export const PASSWORD_RULES = [
  ['too_short', (p) => p.length >= 8],
  ['needs_uppercase', (p) => /[A-Z]/.test(p)],
  ['needs_lowercase', (p) => /[a-z]/.test(p)],
  ['needs_number', (p) => /[0-9]/.test(p)],
  ['needs_symbol', (p) => /[^A-Za-z0-9]/.test(p)],
];
export const passwordIsStrong = (p) => PASSWORD_RULES.every(([, ok]) => ok(p || ''));

export function PasswordMeter({ password }) {
  const t = useTranslations('auth.password');
  const passed = PASSWORD_RULES.filter(([, ok]) => ok(password || '')).length;
  return (
    <div style={{ margin: '-0.35rem 0 0.8rem' }} aria-live="polite">
      <div className="meter-auth" aria-hidden>
        {PASSWORD_RULES.map(([rule], i) => <span key={rule} className={`meter-bar-auth${i < passed ? ` on-${passed}` : ''}`} />)}
      </div>
      <ul className="rules-auth">
        {PASSWORD_RULES.map(([rule, ok]) => {
          const met = ok(password || '');
          return (
            <li key={rule} className={`rule-auth${met ? ' met-auth' : ''}`}>
              <Check aria-hidden style={{ opacity: met ? 1 : 0.35 }} />{t(rule)}
              <span className="sr-only">{met ? t('met') : t('notMet')}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Server-side arithmetic CAPTCHA, challenge and answer side by side. */
export function Captcha({ onChange, reloadKey = 0, error }) {
  const t = useTranslations('auth.captcha');
  const [challenge, setChallenge] = useState(null);
  const [answer, setAnswer] = useState('');
  const [failed, setFailed] = useState(false);
  const id = useId();

  const load = useCallback(async () => {
    setFailed(false);
    setAnswer('');
    try {
      const next = await api.get('/auth/captcha');
      setChallenge(next);
      onChange({ captcha_id: next.captcha_id, captcha_answer: '' });
    } catch {
      setFailed(true);
    }
  }, [onChange]);

  useEffect(() => { Promise.resolve().then(load); }, [load, reloadKey]);

  return (
    <div className="captcha-container-auth">
      <label className="field-label-auth" htmlFor={id}>{t('label')}</label>
      <div className="captcha-row-auth">
        <div className="captcha-challenge-box-auth">
          <span className="captcha-challenge-text-auth" aria-live="polite">
            {failed ? t('unavailable') : challenge?.challenge ?? '· · ·'}
          </span>
          <button type="button" className="captcha-refresh-btn-auth" onClick={load} aria-label={t('refresh')}>
            <RefreshCw aria-hidden />
          </button>
        </div>
        <input id={id} className="field-input-auth" inputMode="numeric" placeholder={t('answer')} value={answer}
          aria-invalid={error ? 'true' : undefined}
          onChange={(e) => {
            const v = e.target.value.replace(/[^\d-]/g, '').slice(0, 5);
            setAnswer(v);
            onChange({ captcha_id: challenge?.captcha_id, captcha_answer: v });
          }} />
      </div>
      {error && <p className="field-error-auth">{error}</p>}
    </div>
  );
}

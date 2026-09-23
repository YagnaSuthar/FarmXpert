'use client';

// ============================================================
// FILE: src/components/auth/forms.jsx
// Login, register, verify email, and forgot/reset password, in the
// reference auth layout. Every error comes from the server's stable
// `code`, translated in messages auth.errors.* - never raw server text.
// ============================================================

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { ArrowLeft, ArrowRight } from '@/components/ui/icons';

import { Link, useRouter } from '@/i18n/navigation';
import { ApiError, api } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import AuthShell from './AuthShell';
import {
  Banner, Captcha, Checkbox, Input, OtpInput, PasswordInput, PasswordMeter, Submit, passwordIsStrong,
} from './widgets';

const EMAIL = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

function useErrorText() {
  const t = useTranslations('auth.errors');
  return useCallback((err) => {
    const code = err instanceof ApiError ? err.code : 'network';
    if (code === 'code_wrong' && err.details?.attempts_left !== undefined) {
      return t('code_wrong_left', { count: err.details.attempts_left });
    }
    return t.has(code) ? t(code) : t('generic');
  }, [t]);
}

/** Once signed in: finish onboarding first, then the dashboard (or a safe ?next=). */
function useAfterLogin() {
  const router = useRouter();
  const search = useSearchParams();
  return useCallback((user) => {
    const next = search.get('next');
    const safe = next && next.startsWith('/') && !next.startsWith('//') ? next : '/dashboard';
    router.replace(user.onboarded ? safe : '/onboarding');
  }, [router, search]);
}

function useRedirectSignedIn() {
  const { status, user } = useAuth();
  const after = useAfterLogin();
  useEffect(() => {
    if (status === 'authenticated' && user) after(user);
  }, [status, user, after]);
}

function Head({ eyebrow, title, accent, children }) {
  return (
    <header className="form-head-auth">
      {eyebrow && <p className="form-eyebrow-auth">{eyebrow}</p>}
      <h1 className="form-title-auth">{title} {accent && <em>{accent}</em>}</h1>
      {children}
    </header>
  );
}

// ── login ───────────────────────────────────────────────────────────────────

export function LoginForm() {
  const t = useTranslations('auth.login');
  const c = useTranslations('auth.common');
  const errorText = useErrorText();
  const after = useAfterLogin();
  const router = useRouter();
  const search = useSearchParams();
  const { login } = useAuth();
  useRedirectSignedIn();

  const [form, setForm] = useState({ email: search.get('email') || '', password: '', remember: true });
  const [captcha, setCaptcha] = useState(null);
  const [needsCaptcha, setNeedsCaptcha] = useState(false);
  const [captchaKey, setCaptchaKey] = useState(0);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const notice = search.get('verified') ? t('verifiedNotice') : search.get('reset') ? t('resetNotice') : null;

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    if (!EMAIL.test(form.email.trim())) return setError(t('emailInvalid'));
    if (!form.password) return setError(t('passwordMissing'));
    if (needsCaptcha && !captcha?.captcha_answer) return setError(t('captchaMissing'));
    setBusy(true);
    try {
      const user = await login({ ...form, email: form.email.trim(), ...(needsCaptcha ? captcha : {}) });
      after(user);
    } catch (err) {
      if (err.code === 'email_unverified') {
        router.push(`/auth/verify-email?email=${encodeURIComponent(form.email.trim())}&resend=1`);
        return undefined;
      }
      if (err.details?.captcha_required || needsCaptcha) {
        setNeedsCaptcha(true);
        setCaptchaKey((k) => k + 1);
      }
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
    return undefined;
  };

  return (
    <AuthShell art="login">
      <Head eyebrow={t('eyebrow')} title={t('title')} accent={t('titleScript')}>
        <p className="form-sub-auth">
          {t('noAccount')} <Link href="/auth/register" className="link-auth">{t('createOne')}</Link>
        </p>
      </Head>
      <Banner tone="success">{notice}</Banner>
      <Banner>{error}</Banner>
      <form className="login-form-auth" onSubmit={submit} noValidate>
        <Input label={c('email')} type="email" autoComplete="email" inputMode="email" placeholder="you@example.com"
          value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} disabled={busy} />
        <PasswordInput label={c('password')} autoComplete="current-password" placeholder="••••••••" showLabel={c('show')}
          hideLabel={c('hide')} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} disabled={busy} />
        {needsCaptcha && <Captcha onChange={setCaptcha} reloadKey={captchaKey} />}
        <div className="field-row-auth">
          <Checkbox checked={form.remember} onChange={(v) => setForm({ ...form, remember: v })}>{t('remember')}</Checkbox>
          <Link href="/auth/forgot-password" className="link-muted-auth">{t('forgot')}</Link>
        </div>
        <Submit busy={busy}>{t('submit')} <ArrowRight aria-hidden /></Submit>
      </form>
    </AuthShell>
  );
}

// ── register ────────────────────────────────────────────────────────────────

export function RegisterForm({ locale }) {
  const t = useTranslations('auth.register');
  const c = useTranslations('auth.common');
  const errorText = useErrorText();
  const router = useRouter();
  useRedirectSignedIn();

  const [form, setForm] = useState({ name: '', email: '', phone: '', password: '' });
  const [captcha, setCaptcha] = useState(null);
  const [captchaKey, setCaptchaKey] = useState(0);
  const [agree, setAgree] = useState(false);
  const [problems, setProblems] = useState({});
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    const next = {};
    if (form.name.trim().length < 2) next.name = t('nameShort');
    if (!EMAIL.test(form.email.trim())) next.email = t('emailInvalid');
    if (form.phone && !/^[0-9+][0-9]{7,14}$/.test(form.phone.replace(/\s/g, ''))) next.phone = t('phoneInvalid');
    if (!passwordIsStrong(form.password)) next.password = t('passwordWeak');
    if (!captcha?.captcha_answer) next.captcha = t('captchaMissing');
    if (!agree) next.agree = t('agreeMissing');
    setProblems(next);
    setError(null);
    if (Object.keys(next).length) return;
    setBusy(true);
    try {
      const email = form.email.trim().toLowerCase();
      await api.post('/auth/register', {
        name: form.name.trim(), email, password: form.password, language: locale,
        ...(form.phone && { phone: form.phone.replace(/\s/g, '') }), ...captcha,
      });
      router.push(`/auth/verify-email?email=${encodeURIComponent(email)}`);
    } catch (err) {
      setCaptchaKey((k) => k + 1);     // a captcha is single-use, even when the rest failed
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell art="register" wide>
      <Head eyebrow={t('eyebrow')} title={t('title')} accent={t('titleScript')}>
        <p className="form-sub-auth">
          {t('haveAccount')} <Link href="/auth/login" className="link-auth">{t('signIn')}</Link>
        </p>
      </Head>
      <Banner>{error}</Banner>
      <form className="login-form-auth" onSubmit={submit} noValidate style={{ marginTop: '1rem' }}>
        <div className="fields-grid-2x2-auth">
          <Input label={t('name')} autoComplete="name" value={form.name} onChange={set('name')} error={problems.name} disabled={busy} />
          <Input label={t('phone')} optional={c('optional')} type="tel" inputMode="tel" autoComplete="tel" placeholder="+91 98765 43210"
            value={form.phone} onChange={set('phone')} error={problems.phone} disabled={busy} />
        </div>
        <Input label={c('email')} type="email" autoComplete="email" inputMode="email" placeholder="you@example.com"
          value={form.email} onChange={set('email')} error={problems.email} disabled={busy} />
        <PasswordInput label={c('password')} autoComplete="new-password" placeholder="••••••••" showLabel={c('show')}
          hideLabel={c('hide')} value={form.password} onChange={set('password')} error={problems.password} disabled={busy} />
        {form.password && <PasswordMeter password={form.password} />}
        <Captcha onChange={setCaptcha} reloadKey={captchaKey} error={problems.captcha} />
        <div style={{ margin: '0.1rem 0 0.9rem' }}>
          <Checkbox top checked={agree} onChange={setAgree} invalid={Boolean(problems.agree)}>{t('agree')}</Checkbox>
          {problems.agree && <p className="field-error-auth">{problems.agree}</p>}
        </div>
        <Submit busy={busy}>{t('submit')} <ArrowRight aria-hidden /></Submit>
      </form>
    </AuthShell>
  );
}

// ── verify email ────────────────────────────────────────────────────────────

const RESEND_WAIT_S = 45;

export function VerifyEmailForm() {
  const t = useTranslations('auth.verify');
  const errorText = useErrorText();
  const router = useRouter();
  const search = useSearchParams();
  const email = search.get('email') || '';
  const [code, setCode] = useState('');
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  const [wait, setWait] = useState(RESEND_WAIT_S);

  useEffect(() => {
    if (wait <= 0) return undefined;
    const timer = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(timer);
  }, [wait]);

  const resend = useCallback(async () => {
    setError(null);
    try {
      await api.post('/auth/resend-code', { email });
      setNotice(t('resent'));
      setWait(RESEND_WAIT_S);
    } catch (err) {
      setError(errorText(err));
    }
  }, [email, errorText, t]);

  // Arrived from a login with an unverified address: send a fresh code once.
  useEffect(() => {
    if (search.get('resend') === '1' && email) Promise.resolve().then(resend);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (value = code) => {
    if (value.length !== 6) return;
    setBusy(true);
    setError(null);
    try {
      await api.post('/auth/verify-email', { email, code: value });
      router.replace(`/auth/login?verified=1&email=${encodeURIComponent(email)}`);
    } catch (err) {
      setError(errorText(err));
      setCode('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell art="verify">
      <Head eyebrow={t('eyebrow')} title={t('title')} accent={t('titleScript')}>
        <p className="form-sub-auth">{t.rich('subtitle', { email: () => <strong>{email}</strong> })}</p>
      </Head>
      <Banner>{error}</Banner>
      <Banner tone="success">{notice}</Banner>
      <div className="otp-container-auth">
        <OtpInput value={code} label={t('codeLabel')} invalid={Boolean(error)} disabled={busy}
          onChange={(v) => { setCode(v); if (v.length === 6) submit(v); }} />
        <Submit type="button" busy={busy} disabled={code.length !== 6} onClick={() => submit()}>{t('submit')}</Submit>
        <div className="otp-resend-row-auth">
          {wait > 0 ? <span>{t('resendIn', { seconds: wait })}</span>
            : <button type="button" className="btn-link-auth" onClick={resend}>{t('resend')}</button>}
        </div>
      </div>
      <div className="back-link-wrap-auth">
        <Link href="/auth/register" className="nav-back-auth"><ArrowLeft aria-hidden />{t('wrongEmail')}</Link>
      </div>
    </AuthShell>
  );
}

// ── forgot / reset password ─────────────────────────────────────────────────

export function ForgotPasswordFlow() {
  const t = useTranslations('auth.forgot');
  const c = useTranslations('auth.common');
  const errorText = useErrorText();
  const router = useRouter();
  const [step, setStep] = useState('email');        // email -> code -> password
  const [email, setEmail] = useState('');
  const [captcha, setCaptcha] = useState(null);
  const [captchaKey, setCaptchaKey] = useState(0);
  const [code, setCode] = useState('');
  const [resetToken, setResetToken] = useState(null);
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const index = { email: 1, code: 2, password: 3 }[step];

  const run = async (fn) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(errorText(err));
      if (step === 'email') setCaptchaKey((k) => k + 1);
      if (err.code === 'reset_expired') setStep('email');
    } finally {
      setBusy(false);
    }
  };

  const head = {
    email: [t('titleEmail'), t('subtitleEmail')],
    code: [t('titleCode'), t.rich('subtitleCode', { email: () => <strong>{email}</strong> })],
    password: [t('titlePassword'), t('subtitlePassword')],
  }[step];

  return (
    <AuthShell art={step === 'email' ? 'forgot' : 'reset'}>
      <Head eyebrow={t('eyebrow', { step: index })} title={head[0]}>
        <p className="form-sub-auth">{head[1]}</p>
      </Head>
      <div className="steps-auth" aria-hidden>
        {[1, 2, 3].map((n) => <span key={n} className={`step-auth${n <= index ? ' on-auth' : ''}`} />)}
      </div>
      <Banner>{error}</Banner>

      {step === 'email' && (
        <form className="login-form-auth" style={{ marginTop: '0.4rem' }} noValidate onSubmit={(e) => {
          e.preventDefault();
          if (!EMAIL.test(email.trim())) return setError(t('emailInvalid'));
          if (!captcha?.captcha_answer) return setError(t('captchaMissing'));
          return run(async () => {
            await api.post('/auth/forgot-password', { email: email.trim().toLowerCase(), ...captcha });
            setStep('code');
          });
        }}>
          <Input label={c('email')} type="email" autoComplete="email" placeholder="you@example.com" value={email}
            onChange={(e) => setEmail(e.target.value)} disabled={busy} />
          <Captcha onChange={setCaptcha} reloadKey={captchaKey} />
          <Submit busy={busy}>{t('sendCode')} <ArrowRight aria-hidden /></Submit>
        </form>
      )}

      {step === 'code' && (
        <div className="otp-container-auth" style={{ marginTop: '0.4rem' }}>
          <OtpInput value={code} label={t('codeLabel')} invalid={Boolean(error)} disabled={busy} onChange={(v) => {
            setCode(v);
            if (v.length === 6) {
              run(async () => {
                const res = await api.post('/auth/verify-reset-code', { email: email.trim().toLowerCase(), code: v });
                setResetToken(res.reset_token);
                setStep('password');
              }).then(() => setCode(''));
            }
          }} />
          <p className="form-sub-auth" style={{ textAlign: 'right' }}>{t('codeHint')}</p>
        </div>
      )}

      {step === 'password' && (
        <form className="login-form-auth" style={{ marginTop: '0.4rem' }} noValidate onSubmit={(e) => {
          e.preventDefault();
          if (!passwordIsStrong(password)) return setError(t('passwordWeak'));
          return run(async () => {
            await api.post('/auth/reset-password', { reset_token: resetToken, password });
            router.replace('/auth/login?reset=1');
          });
        }}>
          <PasswordInput label={t('newPassword')} autoComplete="new-password" autoFocus showLabel={c('show')} hideLabel={c('hide')}
            value={password} onChange={(e) => setPassword(e.target.value)} disabled={busy} />
          {password && <PasswordMeter password={password} />}
          <Submit busy={busy}>{t('save')}</Submit>
        </form>
      )}

      <div className="back-link-wrap-auth">
        <Link href="/auth/login" className="nav-back-auth"><ArrowLeft aria-hidden />{t('back')}</Link>
      </div>
    </AuthShell>
  );
}

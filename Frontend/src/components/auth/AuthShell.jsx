'use client';

// ============================================================
// FILE: src/components/auth/AuthShell.jsx
//
// The frame every auth screen sits in - the reference layout:
//   a rectangular card; the form on the left; a low-poly mesh art
//   panel cut in on a diagonal on the right, with its story copy.
// Aaurawell touches: forest-and-gold mesh, a gold hairline inset
// frame, and a script accent line.
// On phones the art becomes a band above the form, as in the reference.
// ============================================================

import { Suspense, useTransition } from 'react';
import { Languages, Monitor, Moon, Sun } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';

import { Link, usePathname, useRouter } from '@/i18n/navigation';
import { locales } from '@/i18n/routing';
import { useTheme } from '@/components/theme/ThemeProvider';
import AuthMeshArt from './AuthMeshArt';

function BrandMark() {
  return (
    <svg className="brand-mark-auth" viewBox="0 0 32 32" aria-hidden="true">
      <polygon points="16,2 30,11 30,23 16,30 2,23 2,11" fill="none" stroke="url(#fxBrandAuth)" strokeWidth="2" />
      <polygon points="16,2 30,11 16,16" fill="url(#fxBrandAuth)" opacity="0.9" />
      <polygon points="16,16 30,11 30,23 16,30" fill="url(#fxBrandAuth)" opacity="0.55" />
      <polygon points="16,16 2,11 2,23 16,30" fill="url(#fxBrandAuth)" opacity="0.3" />
      <defs>
        <linearGradient id="fxBrandAuth" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#0f4a2e" />
          <stop offset="60%" stopColor="#2f7a3e" />
          <stop offset="100%" stopColor="#b8913a" />
        </linearGradient>
      </defs>
    </svg>
  );
}

function LocaleChip() {
  const t = useTranslations('languageSwitcher');
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const [pending, start] = useTransition();
  return (
    <label className="chip-auth">
      <Languages aria-hidden />
      <span className="sr-only">{t('label')}</span>
      <select value={locale} disabled={pending} onChange={(e) => {
        const q = search.toString();
        start(() => router.replace(q ? `${pathname}?${q}` : pathname, { locale: e.target.value }));
      }}>
        {locales.map((code) => <option key={code} value={code}>{t(code)}</option>)}
      </select>
    </label>
  );
}

function ThemeChip() {
  const { mode, setMode } = useTheme();
  const t = useTranslations('app.theme');
  const order = ['light', 'dark', 'system'];
  const next = order[(order.indexOf(mode) + 1) % order.length];
  const Icon = mode === 'light' ? Sun : mode === 'dark' ? Moon : Monitor;
  return (
    <button type="button" className="chip-auth icon-auth" onClick={() => setMode(next)}
      aria-label={t('switchTo', { mode: t(next) })} title={t(mode)}>
      <Icon aria-hidden />
    </button>
  );
}

export default function AuthShell({ art = 'login', wide = false, children }) {
  const t = useTranslations('auth.art');
  return (
    <main className="auth-viewport-auth">
      <div className="topbar-auth">
        <Suspense><LocaleChip /></Suspense>
        <ThemeChip />
      </div>

      <div className="page-auth">
        <section className="panel-form-auth">
          <div className={`form-wrap-auth${wide ? ' wide-auth' : ''}`}>
            <Link href="/" className="brand-auth" aria-label="FarmXpert">
              <BrandMark />
              <span className="brand-name-auth">FARM<b>X</b>PERT</span>
            </Link>
            {children}
          </div>
        </section>

        <section className="panel-art-auth" aria-hidden="true">
          <AuthMeshArt />
          <div className="art-copy-auth">
            <p className="art-kicker-auth">{t(`${art}.kicker`)}</p>
            <h2 className="art-title-auth">{t(`${art}.title`)}</h2>
            <p className="art-script-auth">{t(`${art}.script`)}</p>
            <p className="art-sub-auth">{t(`${art}.sub`)}</p>
          </div>
        </section>
      </div>
    </main>
  );
}

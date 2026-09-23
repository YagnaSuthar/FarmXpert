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
import { Languages, Moon, Sun } from '@/components/ui/icons';
import { useLocale, useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';

import { Link, usePathname, useRouter } from '@/i18n/navigation';
import { locales } from '@/i18n/routing';
import { useTheme } from '@/components/theme/ThemeProvider';
import Botanical from '@/components/ui/Botanical';
import { LogoMark, Wordmark } from '@/components/ui/Logo';
import AuthMeshArt from './AuthMeshArt';

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
  const next = mode === 'dark' ? 'light' : 'dark';
  const Icon = mode === 'dark' ? Moon : Sun;
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
      {/* Aaurawell botanicals framing the card, swaying gently in the margins */}
      <div className="leaves-auth" aria-hidden="true">
        <Botanical name="tropical" priority className="leaf-auth leaf-tl-auth" />
        <Botanical name="fern" className="leaf-auth leaf-bl-auth" />
        <Botanical name="eucalyptus" className="leaf-auth leaf-tr-auth" />
        <Botanical name="corner" className="leaf-auth leaf-br-auth" />
        <Botanical name="leaf" className="leaf-auth leaf-float-auth leaf-f1-auth" />
        <Botanical name="leafLight" className="leaf-auth leaf-float-auth leaf-f2-auth" />
        <Botanical name="leaf" className="leaf-auth leaf-float-auth leaf-f3-auth" />
      </div>
      <div className="topbar-auth">
        <Suspense><LocaleChip /></Suspense>
        <ThemeChip />
      </div>

      <div className="page-auth">
        <section className="panel-form-auth">
          <div className={`form-wrap-auth${wide ? ' wide-auth' : ''}`}>
            <Link href="/" className="brand-auth" aria-label="FarmXpert">
              <LogoMark className="h-9" />
              <Wordmark className="h-5" />
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

'use client';

// ============================================================
// FILE: src/components/Navbar.jsx
//
// All navigation strings come from `messages.navbar.*`.
// Internal links route through the i18n-aware <Link> so the
// active locale prefix is preserved automatically.
//
// Layout note: the section anchor links live in .nav-links,
// which is hidden under 768px wide. The language switcher and
// CTA live in .nav-actions, which stays visible on mobile —
// language selection must never disappear behind a breakpoint.
// ============================================================

import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import LandingThemeToggle from '@/components/LandingThemeToggle';
import '@/styles/navbar.css';

export default function Navbar() {
  const t = useTranslations('navbar');

  return (
    <nav>
      <Link href="/" className="nav-logo">
        Farm<span>X</span>pert
      </Link>

      <div className="nav-links">
        <a href="#agents">{t('agents')}</a>
        <a href="#features">{t('features')}</a>
        <a href="#how">{t('howItWorks')}</a>
        <a href="#tech">{t('technology')}</a>
      </div>

      <div className="nav-actions">
        <LandingThemeToggle label={t('theme')} />
        <LanguageSwitcher />
        <Link href="/auth/register" className="nav-cta">
          {t('getStarted')}
        </Link>
      </div>
    </nav>
  );
}

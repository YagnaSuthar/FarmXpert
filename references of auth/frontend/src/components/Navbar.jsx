'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Link, usePathname } from '@/i18n/navigation';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { usePageTransition } from '@/reusablefiles/pagetransition';
import { useAuth } from '@/context/AuthContext';
import '@/styles/navbar.css';

/**
 * Navbar component
 * Renders logo, navigation anchor links, language switcher, and conditional CTA button.
 * On Auth pages, Dashboard pages, or whenever authenticated, the CTA button is hidden strictly.
 */
export default function Navbar({ hideCta = false }) {
  const t = useTranslations('navbar');
  const pathname = usePathname();
  const { trigger } = usePageTransition();
  const { isAuthenticated } = useAuth();
  const [currentPath, setCurrentPath] = useState('');

  useEffect(() => {
    if (typeof window !== 'undefined') {
      setCurrentPath(window.location.pathname);
    }
  }, [pathname]);

  const isAuthPage =
    pathname?.includes('/auth') ||
    currentPath?.includes('/auth') ||
    (typeof window !== 'undefined' && window.location.pathname.includes('/auth'));

  const isDashboardPage =
    pathname?.includes('/dashboard') ||
    currentPath?.includes('/dashboard') ||
    (typeof window !== 'undefined' && window.location.pathname.includes('/dashboard'));

  const shouldHideCta = hideCta || isAuthPage || isDashboardPage || isAuthenticated;

  const handleGetStarted = (e) => {
    e.preventDefault();
    trigger({
      to: '/auth/login',
      text: 'Initializing Furnova',
      subtitle: 'Preparing sign-in workspace',
    });
  };

  return (
    <nav className={isAuthPage || isDashboardPage ? 'nav-auth-page' : ''}>
      <Link href="/" className="nav-logo">
        Furn<span>o</span>va
      </Link>

      <div className="nav-links">
        <Link href={isAuthPage || isDashboardPage ? "/#agents" : "#agents"}>{t('agents')}</Link>
        <Link href={isAuthPage || isDashboardPage ? "/#features" : "#features"}>{t('features')}</Link>
        <Link href={isAuthPage || isDashboardPage ? "/#how" : "#how"}>{t('howItWorks')}</Link>
        <Link href={isAuthPage || isDashboardPage ? "/#tech" : "#tech"}>{t('technology')}</Link>
      </div>

      <div className="nav-actions">
        <LanguageSwitcher />
        {!shouldHideCta && (
          <a href="/auth/login" onClick={handleGetStarted} className="nav-cta">
            {t('getStarted')}
          </a>
        )}
      </div>
    </nav>
  );
}

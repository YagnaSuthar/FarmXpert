'use client';

import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';
import Navbar from '@/components/Navbar';
import { usePageTransition } from '@/reusablefiles/pagetransition';
import AuthMeshArt from './AuthMeshArt';

/**
 * AuthLayout - Master split layout for all authentication pages
 * Includes Navbar at top (with CTA hidden).
 * Left: Form panel with brand logo & dynamic form view
 * Right: Geometric mesh art panel with contextual storytelling copy
 * Synchronized with PageTransition so the card entrance animation triggers right as loading panels reveal.
 * Every CSS class strictly adheres to the '-auth' suffix rule.
 */
export default function AuthLayout({
  children,
  artTitle,
  artSubtitle,
}) {
  const t = useTranslations('auth');
  const { state } = usePageTransition();
  const [isRevealed, setIsRevealed] = useState(false);

  useEffect(() => {
    // Trigger card entrance animation when loading panels start revealing (EXITING or IDLE)
    if (state.status === 'IDLE' || state.status === 'EXITING') {
      const timer = setTimeout(() => {
        setIsRevealed(true);
      }, 100);
      return () => clearTimeout(timer);
    } else {
      setIsRevealed(false);
    }
  }, [state.status]);

  return (
    <>
      <Navbar hideCta={true} />
      <main className="auth-viewport-auth">
        <div className={`page-auth ${isRevealed ? 'revealed-auth' : 'preparing-auth'}`}>
          {/* LEFT: FORM */}
          <section className="panel-form-auth">
            <div className="form-wrap-auth">
              {/* Brand Header */}
              <Link href="/" className="brand-auth" aria-label={t('brandName')}>
                <svg className="brand-mark-auth" viewBox="0 0 32 32" aria-hidden="true">
                  <polygon
                    points="16,2 30,11 30,23 16,30 2,23 2,11"
                    fill="none"
                    stroke="url(#brandGradAuth)"
                    strokeWidth="2"
                  />
                  <polygon points="16,2 30,11 16,16" fill="url(#brandGradAuth)" opacity="0.9" />
                  <polygon points="16,16 30,11 30,23 16,30" fill="url(#brandGradAuth)" opacity="0.55" />
                  <polygon points="16,16 2,11 2,23 16,30" fill="url(#brandGradAuth)" opacity="0.3" />
                  <defs>
                    <linearGradient id="brandGradAuth" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stopColor="#000080" />
                      <stop offset="100%" stopColor="#22a8e0" />
                    </linearGradient>
                  </defs>
                </svg>
                <span className="brand-name-auth">{t('brandName')}</span>
              </Link>

              {/* Injected Form Component */}
              {children}
            </div>
          </section>

          {/* RIGHT: ARTWORK (Diagonal Split Overlay) */}
          <section className="panel-art-auth" aria-hidden="true">
            <AuthMeshArt />
            <div className="art-copy-auth">
              <h2 className="art-title-auth">{artTitle}</h2>
              <p className="art-sub-auth">{artSubtitle}</p>
            </div>
          </section>
        </div>
      </main>
    </>
  );
}

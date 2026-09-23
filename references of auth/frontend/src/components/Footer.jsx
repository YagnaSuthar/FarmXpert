'use client';

// ============================================================
// FILE: src/components/Footer.jsx
//
// Copyright string uses an ICU placeholder — {year} — that
// next-intl substitutes at render time. We compute the year on
// the client so it's always current without needing to ship a
// build-time substitution.
// ============================================================

import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';

export default function Footer() {
  const t = useTranslations('footer');
  const tLinks = useTranslations('footer.links');

  return (
    <footer>
      <Link href="/" className="footer-logo">
        Furn<span>o</span>va
      </Link>

      <div className="footer-copy">
        {t('copyright', { year: new Date().getFullYear() })}
      </div>

      <div className="footer-links">
        <Link href="/privacy">{tLinks('privacy')}</Link>
        <Link href="/terms">{tLinks('terms')}</Link>
        <Link href="/docs">{tLinks('docs')}</Link>
        <Link href="/contact">{tLinks('contact')}</Link>
      </div>
    </footer>
  );
}

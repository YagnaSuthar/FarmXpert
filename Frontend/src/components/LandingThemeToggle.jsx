'use client';

// ============================================================
// FILE: src/components/LandingThemeToggle.jsx
//
// Light / dark switch for the landing page. Sets <html data-theme>,
// stores the choice in the shared `fx_theme` cookie (the app reads it
// too), and tells the canvas animations to repaint in the new palette.
// ============================================================

import { useState } from 'react';

export default function LandingThemeToggle({ label = 'Switch theme' }) {
  const [theme, setTheme] = useState(() => (typeof document === 'undefined'
    ? 'dark' : document.documentElement.dataset.theme || 'dark'));

  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    document.cookie = `fx_theme=${next}; path=/; max-age=31536000; samesite=lax`;
    window.dispatchEvent(new CustomEvent('fx-theme', { detail: next }));
    setTheme(next);
  };

  return (
    <button type="button" className="theme-toggle" onClick={toggle} aria-label={label} title={label}
      suppressHydrationWarning>
      {/* both drawn; CSS shows the one for the current theme, so SSR and client agree */}
      <svg className="theme-toggle__sun" viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8" />
      </svg>
      <svg className="theme-toggle__moon" viewBox="0 0 24 24" aria-hidden>
        <path d="M19.5 14.5A8 8 0 1 1 9.5 4.5a6.5 6.5 0 0 0 10 10z" />
      </svg>
    </button>
  );
}

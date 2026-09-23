'use client';

// ============================================================
// FILE: src/components/theme/ThemeProvider.jsx
//
// Light or dark for the app (light by default). The choice is a
// cookie the server reads when rendering, so the first paint is
// already in the right theme - no flash, no inline script.
// ============================================================

import { createContext, useCallback, useContext, useState } from 'react';
import { Moon, Sun } from '@/components/ui/icons';
import { useTranslations } from 'next-intl';

import { cn } from '@/lib/cn';

export const THEME_COOKIE = 'fx_theme';
const ThemeContext = globalThis.__fxThemeContext ??= createContext(null);   // one instance (see AuthContext)

export function ThemeProvider({ initial = 'light', children, className }) {
  const [mode, setModeState] = useState(initial);

  const setMode = useCallback((next) => {
    setModeState(next);
    document.cookie = `${THEME_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
  }, []);

  return (
    <ThemeContext.Provider value={{ mode, setMode }}>
      <div className={cn('fx-app', className)} data-mode={mode}>{children}</div>
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}

const MODES = [
  { value: 'light', icon: Sun },
  { value: 'dark', icon: Moon },
];

/** Two-way segmented switch. `compact` shows a single cycling button. */
export function ThemeToggle({ compact = false, className }) {
  const { mode, setMode } = useTheme();
  const t = useTranslations('app.theme');
  if (compact) {
    const index = MODES.findIndex((m) => m.value === mode);
    const current = MODES[index] || MODES[0];
    const next = MODES[(index + 1) % MODES.length];
    return (
      <button type="button" onClick={() => setMode(next.value)}
        className={cn('grid size-10 place-items-center rounded-full border border-line bg-surface text-muted transition-colors hover:text-ink', className)}
        aria-label={t('switchTo', { mode: t(next.value) })} title={t(current.value)}>
        <current.icon className="size-4.5" />
      </button>
    );
  }
  return (
    <div role="radiogroup" aria-label={t('label')}
      className={cn('inline-flex rounded-full border border-line bg-surface p-1', className)}>
      {MODES.map(({ value, icon: Icon }) => (
        <button key={value} type="button" role="radio" aria-checked={mode === value} onClick={() => setMode(value)}
          className={cn('inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs transition-all',
            mode === value ? 'bg-forest text-on-forest shadow-card' : 'text-muted hover:text-ink')}>
          <Icon className="size-3.5" aria-hidden />{t(value)}
        </button>
      ))}
    </div>
  );
}

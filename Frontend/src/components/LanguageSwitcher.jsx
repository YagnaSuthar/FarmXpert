'use client';

// ============================================================
// FILE: src/components/LanguageSwitcher.jsx
//
// Native <select>-based language switcher.
//
// Why <select> over a custom dropdown:
//   - Keyboard accessibility, screen reader announcement,
//     and mobile native pickers come for free.
//   - No outside-click / focus-trap logic to maintain.
//   - Submits without page reload — we route programmatically.
//
// How the switch works:
//   1. onChange fires with the new locale code.
//   2. We call router.replace() from next-intl's locale-aware
//      navigation, which preserves the current pathname + query.
//   3. The middleware sees the new prefix, writes the
//      NEXT_LOCALE cookie, and re-renders the page.
// No client-side reload — Next handles the transition.
// ============================================================

import { useTransition } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { usePathname, useRouter } from '@/i18n/navigation';
import { locales } from '@/i18n/routing';

export default function LanguageSwitcher() {
  const t = useTranslations('languageSwitcher');
  const router = useRouter();
  const pathname = usePathname();
  const activeLocale = useLocale();

  // useTransition gives us an `isPending` flag so we can disable
  // the control during navigation. Avoids users firing two
  // switches in a row and ending up on the wrong locale.
  const [isPending, startTransition] = useTransition();

  function onChange(event) {
    const nextLocale = event.target.value;
    if (nextLocale === activeLocale) return;
    startTransition(() => {
      // pathname here is the locale-stripped path (e.g. "/", "/about");
      // router.replace re-prefixes it correctly for the new locale.
      router.replace(pathname, { locale: nextLocale });
    });
  }

  return (
    <label className="lang-switcher" data-pending={isPending || undefined}>
      <span className="lang-switcher__label">{t('label')}</span>
      <select
        className="lang-switcher__select"
        value={activeLocale}
        onChange={onChange}
        disabled={isPending}
        aria-label={t('label')}
      >
        {locales.map((code) => (
          <option key={code} value={code}>
            {t(code)}
          </option>
        ))}
      </select>
    </label>
  );
}

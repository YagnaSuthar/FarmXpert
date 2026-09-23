// ============================================================
// FILE: src/i18n/routing.js
//
// Single source of truth for the i18n routing configuration.
// Used by:
//   - src/middleware.js          (locale negotiation + cookie writing)
//   - src/i18n/navigation.js     (locale-aware Link, router, redirect)
//   - src/i18n/request.js        (server-side message loading)
//   - src/app/[locale]/layout.jsx (locale validation, static params)
//
// To add a new locale (e.g. Bengali):
//   1. Add the BCP-47 code to `locales` below.
//   2. Add a matching `src/messages/<code>.json`.
//   3. Add a label entry in messages → `languageSwitcher`.
//   4. Done — no component code changes needed.
// ============================================================

import { defineRouting } from 'next-intl/routing';

/**
 * @typedef {'en' | 'hi' | 'gu'} Locale
 */

/**
 * The full list of locales the app ships. Order matters: it controls the
 * default order in the language switcher. The default locale must be present.
 *
 * Keep this list flat (BCP-47 codes only). Display names live in messages
 * under `languageSwitcher.*` so they themselves can be localized.
 */
export const locales = /** @type {const} */ (['en', 'hi', 'gu']);

/** Default locale used when no preference is detected. */
export const defaultLocale = 'en';

/**
 * `as-needed` strategy:
 *   - English routes render at `/`, `/agents`, etc. (no prefix)
 *   - Hindi at `/hi/...`, Gujarati at `/gu/...`
 *
 * This keeps the canonical English URLs clean (better for SEO) while still
 * giving every non-default locale a stable, indexable URL.
 */
export const localePrefix = 'always';

export const routing = defineRouting({
  locales,
  defaultLocale,
  localePrefix,

  // Cookie name next-intl uses to persist the locale across visits.
  // Standard name — also recognised by Next.js's built-in i18n detection.
  localeCookie: {
    name: 'NEXT_LOCALE',
    // 1 year — long enough to feel persistent without being unbounded.
    maxAge: 60 * 60 * 24 * 365,
  },

  // If a path comes in with an unknown / disabled locale prefix, redirect
  // rather than 404. Keeps shared / bookmarked links robust.
  localeDetection: true,
});

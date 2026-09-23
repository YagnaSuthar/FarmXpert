// ============================================================
// FILE: src/i18n/request.js
//
// Server-side message resolver. next-intl calls this once per request
// to figure out the active locale and which message bundle to ship.
//
// The dynamic `import()` is critical: it means we only load the JSON
// for the active locale, not all of them. Adding a 20th language won't
// bloat the bundle for users on English.
// ============================================================

import { getRequestConfig } from 'next-intl/server';
import { hasLocale } from 'next-intl';
import { routing } from './routing';

export default getRequestConfig(async ({ requestLocale }) => {
  // requestLocale is what the middleware/segment matched. Validate it
  // against our declared list — if anything went sideways (e.g. a hand-
  // crafted URL with an unsupported code), fall back to the default.
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested)
    ? requested
    : routing.defaultLocale;

  // Lazy-load just the active bundle. The path is resolved at build time
  // so Next.js can code-split per locale.
  const messages = (await import(`../messages/${locale}.json`)).default;

  return {
    locale,
    messages,
    // Indian Standard Time is the primary audience timezone. Components
    // that format dates/numbers (next-intl's <FormattedDate />, etc.)
    // will pick this up unless they specify their own.
    timeZone: 'Asia/Kolkata',
    // `now` is used by relative-time formatting and is stabilised per
    // request so SSR and client renders agree.
    now: new Date(),
  };
});

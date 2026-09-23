// ============================================================
// FILE: src/middleware.js
//
// Runs on every matching request. next-intl's middleware handles:
//   - Locale negotiation (URL prefix > NEXT_LOCALE cookie >
//     Accept-Language header > defaultLocale)
//   - Writing the NEXT_LOCALE cookie on every locale change, so the
//     user's choice persists across visits without us touching cookies
//     ourselves anywhere else
//   - Rewriting unprefixed URLs to the canonical locale routes
//
// The matcher is restrictive on purpose: we never want this middleware
// to fire on static assets, API routes, or _next internals.
// ============================================================

import createMiddleware from 'next-intl/middleware';
import { routing } from './i18n/routing';

export default createMiddleware(routing);

export const config = {
  // Run on:
  //   - "/"                 (root → defaultLocale)
  //   - "/(en|hi|gu)/..."   (any locale-prefixed route)
  //   - any other app path that isn't a static file or API
  //
  // Skip:
  //   - "/api/*"            (backend / route handlers)
  //   - "/_next/*"          (Next internals + chunks)
  //   - anything with an extension (favicon, images, fonts, etc.)
  matcher: ['/((?!api|_next|_vercel|.*\\..*).*)'],
};

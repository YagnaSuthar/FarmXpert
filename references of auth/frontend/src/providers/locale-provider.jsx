// ============================================================
// FILE: src/providers/locale-provider.jsx
//
// Thin wrapper around NextIntlClientProvider that exists for two reasons:
//   1. Centralise client-provider configuration (error fallbacks,
//      formatting defaults) so individual layouts stay tidy.
//   2. Give us a single place to add additional providers later
//      (theme, analytics, query client) without touching every route.
//
// This component is a Client Component (NextIntlClientProvider must
// run on the client to expose the React context to hooks like
// useTranslations). Messages and locale are passed down from the
// nearest Server Component layout — never fetched here.
// ============================================================

'use client';

import { NextIntlClientProvider } from 'next-intl';
import { AuthProvider } from '@/context/AuthContext';

/**
 * @param {object} props
 * @param {import('react').ReactNode} props.children
 * @param {string} props.locale         Active locale (e.g. 'en')
 * @param {Record<string, unknown>} props.messages  Resolved messages for that locale
 * @param {string} [props.timeZone]     IANA tz; defaults to 'Asia/Kolkata'
 */
export default function LocaleProvider({
  children,
  locale,
  messages,
  timeZone = 'Asia/Kolkata',
}) {
  return (
    <NextIntlClientProvider
      locale={locale}
      messages={messages}
      timeZone={timeZone}
      // In production, missing-key errors should warn but not crash
      // the page. In development we'd rather see the loud error so
      // typos get caught early.
      onError={(error) => {
        // eslint-disable-next-line no-console
        console.warn('[i18n]', error.message);
      }}
      // Fallback strategy: show the key path when a translation is
      // missing so the page still renders. Easier to spot than empty
      // strings, less embarrassing than throwing.
      getMessageFallback={({ namespace, key }) =>
        [namespace, key].filter(Boolean).join('.')
      }
    >
      <AuthProvider>
        {children}
      </AuthProvider>
    </NextIntlClientProvider>
  );
}

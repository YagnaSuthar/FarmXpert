// ============================================================
// FILE: src/app/[locale]/layout.jsx
//
// Nested locale layout. Validates locale param, sets request locale,
// loads translation messages, and provides Locale & PageTransition context.
// ============================================================

import { notFound } from 'next/navigation';
import { hasLocale } from 'next-intl';
import { getMessages, setRequestLocale } from 'next-intl/server';

import { routing } from '@/i18n/routing';
import { localeMetadata } from '@/i18n/metadata';
import LocaleProvider from '@/providers/locale-provider';
import { PageTransitionProvider, PageTransition } from '@/reusablefiles/pagetransition';

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) return {};

  const metadata = localeMetadata[locale];

  return {
    title: metadata.title,
    description: metadata.description,
    keywords: ['accounting', 'double-entry', 'invoicing', 'furniture business', 'Furnova'],
    openGraph: {
      title: metadata.ogTitle,
      description: metadata.ogDescription,
      locale,
      type: 'website',
    },
    twitter: {
      card: 'summary_large_image',
      title: metadata.ogTitle,
      description: metadata.ogDescription,
    },
    alternates: {
      languages: Object.fromEntries(
        routing.locales.map((code) => [code, `/${code}`])
      ),
    },
  };
}

export default async function LocaleLayout({ children, params }) {
  const { locale } = await params;

  if (!hasLocale(routing.locales, locale)) {
    notFound();
  }

  setRequestLocale(locale);

  const messages = await getMessages();

  return (
    <LocaleProvider locale={locale} messages={messages}>
      <PageTransitionProvider>
        <PageTransition />
        <div id="site-root">{children}</div>
      </PageTransitionProvider>
    </LocaleProvider>
  );
}

// ============================================================
// FILE: src/app/[locale]/page.jsx
//
// Locale-aware landing page entry point. Kept thin on purpose:
//   - All composition lives in <LandingPage /> (a Client Component
//     because of the cursor/scroll-reveal effects).
//   - This file is a Server Component so that any per-locale
//     metadata or future static generation work has the right
//     execution context.
// ============================================================

import { setRequestLocale } from 'next-intl/server';

import LandingPage from '@/components/LandingPage';

export default async function Page({ params }) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <LandingPage />;
}

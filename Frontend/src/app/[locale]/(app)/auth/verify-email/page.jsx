import { Suspense } from 'react';
import { getTranslations, setRequestLocale } from 'next-intl/server';

import { VerifyEmailForm } from '@/components/auth/forms';

export async function generateMetadata({ params }) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: 'auth.verify' });
  return { title: `${t('metaTitle')} — FarmXpert` };
}

export default async function Page({ params }) {
  const { locale } = await params;
  setRequestLocale(locale);
  // Suspense: the forms read the query string (?email, ?next).
  return (
    <Suspense>
      <VerifyEmailForm />
    </Suspense>
  );
}

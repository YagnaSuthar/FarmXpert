import { Suspense } from 'react';
import { getTranslations, setRequestLocale } from 'next-intl/server';

import { LoginForm } from '@/components/auth/forms';

export async function generateMetadata({ params }) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: 'auth.login' });
  return { title: `${t('metaTitle')} — FarmXpert` };
}

export default async function Page({ params }) {
  const { locale } = await params;
  setRequestLocale(locale);
  // Suspense: the forms read the query string (?email, ?next).
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}

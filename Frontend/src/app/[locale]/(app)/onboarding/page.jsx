import { getTranslations, setRequestLocale } from 'next-intl/server';

import RequireAuth from '@/components/auth/RequireAuth';
import OnboardingWizard from '@/components/onboarding/OnboardingWizard';

export async function generateMetadata({ params }) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: 'onboarding' });
  return { title: `${t('metaTitle')} — FarmXpert` };
}

export default async function OnboardingPage({ params }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <RequireAuth onboarding fallback={<div className="min-h-dvh" />}>
      <OnboardingWizard />
    </RequireAuth>
  );
}

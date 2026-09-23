import { setRequestLocale } from 'next-intl/server';
import LandingPage from '@/components/LandingPage';

export default async function Page({ params }) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <LandingPage />;
}

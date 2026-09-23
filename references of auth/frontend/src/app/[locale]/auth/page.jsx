import { setRequestLocale } from 'next-intl/server';
import AuthPage from '@/components/auth/AuthPage';

export default async function Page({ params }) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <AuthPage initialMode="login" />;
}

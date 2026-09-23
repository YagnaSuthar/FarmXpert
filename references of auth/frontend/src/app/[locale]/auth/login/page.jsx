import { setRequestLocale } from 'next-intl/server';
import AuthPage from '@/components/auth/AuthPage';

export default async function LoginPage({ params }) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <AuthPage initialMode="login" />;
}

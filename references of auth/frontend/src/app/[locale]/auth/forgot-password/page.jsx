import { setRequestLocale } from 'next-intl/server';
import AuthPage from '@/components/auth/AuthPage';

export default async function ForgotPasswordPage({ params }) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <AuthPage initialMode="forgot-password" />;
}

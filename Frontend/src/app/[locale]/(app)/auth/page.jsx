import { redirect } from '@/i18n/navigation';

export default async function AuthIndex({ params }) {
  const { locale } = await params;
  redirect({ href: '/auth/login', locale });
}

import { redirect } from '@/i18n/navigation';

// The assistant now lives in the dashboard.
export default async function ChatRedirect({ params }) {
  const { locale } = await params;
  redirect({ href: '/dashboard/assistant', locale });
}

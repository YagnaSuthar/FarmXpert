'use client';

import { useTransition } from 'react';
import { Languages } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';

import { usePathname, useRouter } from '@/i18n/navigation';
import { locales } from '@/i18n/routing';
import { cn } from '@/lib/cn';

/** Compact language picker for the app screens (the landing page has its own). */
export default function LocaleSelect({ className }) {
  const t = useTranslations('languageSwitcher');
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const [pending, start] = useTransition();

  return (
    <label className={cn('relative inline-flex items-center', className)}>
      <span className="sr-only">{t('label')}</span>
      <Languages className="pointer-events-none absolute left-3 size-4 text-faint" aria-hidden />
      <select
        value={locale}
        disabled={pending}
        onChange={(e) => {
          const query = search.toString();
          start(() => router.replace(query ? `${pathname}?${query}` : pathname, { locale: e.target.value }));
        }}
        className="h-10 appearance-none rounded-full border border-line bg-surface pr-4 pl-9 text-sm text-ink hover:border-leaf/50 focus:outline-none"
      >
        {locales.map((code) => <option key={code} value={code}>{t(code)}</option>)}
      </select>
    </label>
  );
}

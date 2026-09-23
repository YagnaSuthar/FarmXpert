'use client';

// ============================================================
// FILE: src/components/dashboard/DashboardShell.jsx
//
// The signed-in frame, in the Aaurawell design:
//   desktop: a forest sidebar (gold hairline, leaf sprig, script
//            greeting) beside a cream workspace
//   phone:   a slim top bar and a bottom tab bar under the thumb
// ============================================================

import { Suspense, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  BarChart3, ChevronDown, Droplets, FlaskConical, Home, LogOut, MessageCircle, Settings, Sprout, Store,
} from 'lucide-react';

import { Link, usePathname, useRouter } from '@/i18n/navigation';
import { cn } from '@/lib/cn';
import { useAuth } from '@/context/AuthContext';
import { useFarm } from '@/context/FarmContext';
import { clearApiCache } from '@/hooks/useApi';
import Botanical from '@/components/ui/Botanical';
import LocaleSelect from '@/components/ui/LocaleSelect';
import Logo from '@/components/ui/Logo';
import { ThemeToggle } from '@/components/theme/ThemeProvider';

export const NAV = [
  { href: '/dashboard', key: 'overview', icon: Home, mobile: true },
  { href: '/dashboard/assistant', key: 'assistant', icon: MessageCircle, mobile: true },
  { href: '/dashboard/tasks', key: 'tasks', icon: Sprout, mobile: true },
  { href: '/dashboard/irrigation', key: 'irrigation', icon: Droplets, mobile: true },
  { href: '/dashboard/soil', key: 'soil', icon: FlaskConical, mobile: false },
  { href: '/dashboard/market', key: 'market', icon: Store, mobile: true },
  { href: '/dashboard/usage', key: 'usage', icon: BarChart3, mobile: false },
  { href: '/dashboard/settings', key: 'settings', icon: Settings, mobile: false },
];

function isActive(pathname, href) {
  return href === '/dashboard' ? pathname === href : pathname.startsWith(href);
}

function FarmSwitcher({ tone = 'light' }) {
  const t = useTranslations('dashboard.shell');
  const { farms, farm, setFarmId } = useFarm();
  if (!farm) return null;
  const place = [farm.district, farm.state].filter(Boolean).join(', ');
  return (
    <div className={cn('relative rounded-2xl border px-4 py-3',
      tone === 'forest' ? 'border-white/12 bg-white/6 text-white' : 'border-line bg-surface')}>
      <p className={cn('eyebrow', tone === 'forest' ? 'text-gold/90' : 'text-gold')}>{t('farm')}</p>
      <div className="mt-1 flex items-center gap-2">
        <p className="min-w-0 flex-1 truncate font-serif text-lg leading-tight">{farm.name}</p>
        {farms.length > 1 && <ChevronDown className="size-4 opacity-60" aria-hidden />}
      </div>
      {place && <p className={cn('truncate text-xs', tone === 'forest' ? 'text-white/55' : 'text-faint')}>{place}</p>}
      {farms.length > 1 && (
        <select aria-label={t('switchFarm')} value={farm.id} onChange={(e) => setFarmId(e.target.value)}
          className="absolute inset-0 cursor-pointer opacity-0">
          {farms.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      )}
    </div>
  );
}

export default function DashboardShell({ children }) {
  const t = useTranslations('dashboard.nav');
  const s = useTranslations('dashboard.shell');
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const [leaving, setLeaving] = useState(false);
  const initials = (user?.name || '?').split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase();

  const signOut = async () => {
    setLeaving(true);
    await logout();
    clearApiCache();
    router.replace('/auth/login');
  };

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[17.5rem_minmax(0,1fr)]">
      {/* ── sidebar (desktop) ───────────────────────────────── */}
      <aside className="panel-forest sticky top-0 hidden h-dvh flex-col p-5 lg:flex">
        <div className="pointer-events-none absolute inset-3 rounded-[1.6rem] border border-gold/15" aria-hidden />
        <Botanical name="sprig" className="animate-sway -right-20 -bottom-24 w-56 -scale-x-100 opacity-[0.16]" />
        <div className="relative px-2 pt-2"><Logo href="/dashboard" tone="light" /></div>
        <div className="relative mt-7"><FarmSwitcher tone="forest" /></div>

        <nav className="relative mt-6 flex-1 space-y-1 overflow-y-auto no-scrollbar" aria-label={s('menu')}>
          {NAV.map(({ href, key, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <Link key={href} href={href} aria-current={active ? 'page' : undefined}
                className={cn('group relative flex items-center gap-3 rounded-2xl px-4 py-2.5 text-sm transition-all duration-200',
                  active ? 'bg-white/12 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.08)]' : 'text-white/65 hover:bg-white/6 hover:text-white')}>
                {active && <span className="absolute top-1/2 left-0 h-5 w-[3px] -translate-y-1/2 rounded-full bg-gold" aria-hidden />}
                <Icon className={cn('size-[1.15rem]', active ? 'text-gold' : 'text-white/55 group-hover:text-white/80')} aria-hidden />
                {t(key)}
              </Link>
            );
          })}
        </nav>

        <div className="relative mt-4 space-y-3 border-t border-white/10 pt-4">
          <div className="flex items-center justify-between gap-2 px-1">
            <ThemeToggle compact className="border-white/15 bg-white/8 text-white/80 hover:text-white" />
            <Suspense><LocaleSelect className="[&_select]:border-white/15 [&_select]:bg-white/8 [&_select]:text-white [&_svg]:text-white/60" /></Suspense>
          </div>
          <div className="flex items-center gap-3 rounded-2xl bg-white/6 p-2.5">
            <span className="grid size-10 shrink-0 place-items-center rounded-full bg-gold font-serif text-forest-deep">{initials}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-white">{user?.name}</p>
              <p className="truncate text-xs text-white/50">{user?.email}</p>
            </div>
            <button type="button" onClick={signOut} disabled={leaving} aria-label={s('logout')}
              className="grid size-9 place-items-center rounded-full text-white/60 hover:bg-white/10 hover:text-white">
              <LogOut className="size-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* ── workspace ───────────────────────────────────────── */}
      <div className="relative min-w-0 pb-24 lg:pb-0">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-line bg-canvas/85 px-4 backdrop-blur-md lg:hidden">
          <Logo href="/dashboard" />
          <div className="flex items-center gap-2">
            <ThemeToggle compact />
            <Link href="/dashboard/settings" aria-label={t('settings')}
              className="grid size-10 place-items-center rounded-full bg-forest font-serif text-sm text-on-forest">{initials}</Link>
          </div>
        </header>
        <main className="container-app py-6 sm:py-8 lg:py-10">{children}</main>
      </div>

      {/* ── bottom tabs (phone) ─────────────────────────────── */}
      <nav aria-label={s('menu')}
        className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden">
        <ul className="grid grid-cols-5">
          {NAV.filter((n) => n.mobile).map(({ href, key, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <li key={href}>
                <Link href={href} aria-current={active ? 'page' : undefined}
                  className={cn('flex flex-col items-center gap-1 py-2.5 text-[0.68rem] transition-colors',
                    active ? 'text-forest dark:text-leaf' : 'text-faint')}>
                  <span className={cn('grid h-7 w-12 place-items-center rounded-full transition-colors', active && 'bg-sage')}>
                    <Icon className="size-[1.15rem]" aria-hidden />
                  </span>
                  {t(key)}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}

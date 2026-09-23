'use client';

// ============================================================
// FILE: src/components/dashboard/DashboardShell.jsx
//
// The signed-in frame:
//   desktop: the Aaurawell sidebar - white with grey botanicals and a
//            climbing vine in light, deep forest green in dark -
//            beside the workspace
//   phone:   a slim top bar and a bottom tab bar under the thumb
// ============================================================

import { Suspense, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  ChartNoAxesColumn, ChevronsUpDown, Droplets, FlaskConical, House, ListChecks, LogOut, MessagesSquare,
  Settings2, Store,
} from '@/components/ui/icons';

import { Link, usePathname, useRouter } from '@/i18n/navigation';
import { cn } from '@/lib/cn';
import { useAuth } from '@/context/AuthContext';
import SidebarVines from './SidebarVine';
import WelcomeIntro from './WelcomeIntro';
import { useFarm } from '@/context/FarmContext';
import { clearApiCache } from '@/hooks/useApi';
import Botanical from '@/components/ui/Botanical';
import LocaleSelect from '@/components/ui/LocaleSelect';
import Logo from '@/components/ui/Logo';
import { ThemeToggle } from '@/components/theme/ThemeProvider';

export const NAV = [
  { href: '/dashboard', key: 'overview', icon: House, mobile: true, group: 'daily' },
  { href: '/dashboard/assistant', key: 'assistant', icon: MessagesSquare, mobile: true, group: 'daily' },
  { href: '/dashboard/tasks', key: 'tasks', icon: ListChecks, mobile: true, group: 'field' },
  { href: '/dashboard/irrigation', key: 'irrigation', icon: Droplets, mobile: true, group: 'field' },
  { href: '/dashboard/soil', key: 'soil', icon: FlaskConical, mobile: false, group: 'field' },
  { href: '/dashboard/market', key: 'market', icon: Store, mobile: true, group: 'business' },
  { href: '/dashboard/usage', key: 'usage', icon: ChartNoAxesColumn, mobile: false, group: 'business' },
  { href: '/dashboard/settings', key: 'settings', icon: Settings2, mobile: false, group: 'account' },
];

function isActive(pathname, href) {
  return href === '/dashboard' ? pathname === href : pathname.startsWith(href);
}

function FarmSwitcher() {
  const t = useTranslations('dashboard.shell');
  const { farms, farm, setFarmId } = useFarm();
  if (!farm) return null;
  const place = [farm.district, farm.state].filter(Boolean).join(', ');
  return (
    <div className="relative rounded-2xl border border-[var(--sb-line)] bg-[var(--sb-card)] px-4 py-3.5 transition-colors hover:border-[var(--sb-line-strong)]">
      <p className="text-[0.62rem] font-medium tracking-[0.22em] text-[var(--sb-gold)] uppercase">{t('farm')}</p>
      <div className="mt-1.5 flex items-center gap-2">
        <p className="min-w-0 flex-1 truncate font-serif text-[1.15rem] leading-tight text-[var(--sb-text)]">{farm.name}</p>
        {farms.length > 1 && <ChevronsUpDown className="size-3.5 text-[var(--sb-faint)]" strokeWidth={1.6} aria-hidden />}
      </div>
      {place && <p className="mt-0.5 truncate text-xs font-light text-[var(--sb-muted)]">{place}</p>}
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
    <div className="fx-dash-root min-h-dvh lg:grid lg:grid-cols-[18rem_minmax(0,1fr)]">
      {user && <WelcomeIntro user={user} />}
      {/* ── sidebar (desktop) ───────────────────────────────── */}
      <aside className="fx-sidebar sticky top-0 hidden h-dvh flex-col overflow-hidden py-5 pr-7 pl-6 lg:flex">
        {/* background foliage: the Aaurawell set, grey through a filter */}
        <Botanical name="corner" className="fx-sidebar-tree -top-12 -left-14 w-44 -scale-y-100" />
        <Botanical name="fern" className="fx-sidebar-tree top-[38%] -right-16 w-36 -scale-x-100" />
        <Botanical name="eucalyptus" className="fx-sidebar-tree -bottom-20 -left-16 w-48" />
        <Botanical name="leafLight" className="fx-sidebar-tree top-[58%] left-2 w-10 rotate-[-30deg]" />
        <SidebarVines />

        <div className="relative px-1.5 pt-1"><Logo href="/dashboard" tone="sidebar" /></div>
        <div className="relative mt-7 mr-7"><FarmSwitcher /></div>

        <nav className="relative mt-7 flex-1 space-y-1 overflow-y-auto no-scrollbar" aria-label={s('menu')}>
          {NAV.map(({ href, key, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <Link key={href} href={href} aria-current={active ? 'page' : undefined}
                className={cn('group relative flex items-center gap-3.5 rounded-xl px-3.5 py-2.5 text-[0.875rem] tracking-[0.005em] transition-all duration-200',
                  active
                    ? '[background:var(--sb-active)] font-medium text-[var(--sb-active-text)] shadow-[var(--sb-active-shadow)]'
                    : 'font-normal text-[var(--sb-muted)] hover:bg-[var(--sb-hover)] hover:text-[var(--sb-text)]')}>
                {active && <span className="absolute top-1/2 -left-6 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-[var(--sb-gold)]" aria-hidden />}
                <Icon className={cn('size-[1.15rem] shrink-0 transition-colors',
                  active ? 'text-[#ecc868]' : 'text-[var(--sb-faint)] group-hover:text-[var(--sb-muted)]')}
                  strokeWidth={active ? 1.9 : 1.6} aria-hidden />
                {t(key)}
              </Link>
            );
          })}
        </nav>

        <div className="relative mt-4 flex items-center gap-1 border-t border-[var(--sb-line)] pt-3 pr-9 pl-7">
          <ThemeToggle compact className="!size-8 !rounded-lg !border-0 !bg-transparent !text-[var(--sb-faint)] hover:!bg-[var(--sb-hover)] hover:!text-[var(--sb-text)]" />
          <Suspense><LocaleSelect className="min-w-0 flex-1 [&_select]:h-8 [&_select]:w-full [&_select]:rounded-lg [&_select]:border-0 [&_select]:bg-transparent [&_select]:text-[0.8rem] [&_select]:text-[var(--sb-muted)] hover:[&_select]:bg-[var(--sb-hover)] [&_svg]:text-[var(--sb-faint)] [&_option]:text-black" /></Suspense>
          <button type="button" onClick={signOut} disabled={leaving} aria-label={s('logout')} title={s('logout')}
            className="grid size-8 place-items-center rounded-lg text-[var(--sb-faint)] transition-colors hover:bg-[var(--sb-hover)] hover:text-danger">
            <LogOut className="size-4" strokeWidth={1.6} />
          </button>
        </div>
      </aside>

      {/* ── workspace ───────────────────────────────────────── */}
      <div className="relative min-w-0 pb-24 lg:pb-0">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-line bg-canvas px-4 lg:hidden">
          <Logo href="/dashboard" />
          <div className="flex items-center gap-2">
            <ThemeToggle compact />
            <Link href="/dashboard/settings" aria-label={t('settings')}
              className="grid size-9 place-items-center rounded-full bg-forest text-xs font-medium text-on-forest">{initials}</Link>
          </div>
        </header>
        <main className="container-app py-6 sm:py-8 lg:py-10">{children}</main>
      </div>

      {/* ── bottom tabs (phone) ─────────────────────────────── */}
      <nav aria-label={s('menu')}
        className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden">
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

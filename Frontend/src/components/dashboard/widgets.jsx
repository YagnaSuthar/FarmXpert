'use client';

// ============================================================
// FILE: src/components/dashboard/widgets.jsx
// Dashboard building blocks in the Aaurawell language.
// ============================================================

import { useLocale, useTranslations } from 'next-intl';
import { ArrowUpRight } from 'lucide-react';

import { Link } from '@/i18n/navigation';
import { cn } from '@/lib/cn';
import Botanical from '@/components/ui/Botanical';
import { Skeleton } from '@/components/ui/primitives';

export function PageHeader({ eyebrow, title, script, lead, action }) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-2xl">
        {eyebrow && <p className="eyebrow flex items-center gap-3 text-gold"><span className="h-px w-8 bg-gold/60" aria-hidden />{eyebrow}</p>}
        <h1 className="mt-2 text-3xl leading-tight text-forest sm:text-[2.35rem] dark:text-ink">
          {title}{script && <> <span className="font-script text-4xl font-normal text-gold sm:text-5xl">{script}</span></>}
        </h1>
        {lead && <p className="mt-2 text-[0.95rem] leading-relaxed text-muted">{lead}</p>}
      </div>
      {action}
    </div>
  );
}

export function Section({ title, subtitle, href, linkLabel, children, className, bodyClass }) {
  return (
    <section className={cn('rounded-[1.75rem] border border-line bg-surface shadow-card', className)}>
      {(title || href) && (
        <header className="flex items-start justify-between gap-4 px-6 pt-5 pb-1 sm:px-7">
          <div>
            <h2 className="text-xl text-forest dark:text-ink">{title}</h2>
            {subtitle && <p className="mt-0.5 text-sm text-faint">{subtitle}</p>}
          </div>
          {href && (
            <Link href={href} className="inline-flex shrink-0 items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium text-leaf hover:bg-sage">
              {linkLabel}<ArrowUpRight className="size-3.5" aria-hidden />
            </Link>
          )}
        </header>
      )}
      <div className={cn('px-6 pt-3 pb-6 sm:px-7', bodyClass)}>{children}</div>
    </section>
  );
}

/** A number that matters, with a small icon and a plain-words note. */
export function Stat({ icon: Icon, label, value, unit, note, tone = 'leaf', loading }) {
  const tones = {
    leaf: 'bg-sage text-leaf', sky: 'bg-sky/10 text-sky', gold: 'bg-gold-soft text-gold', warn: 'bg-warn/12 text-warn',
    danger: 'bg-danger/10 text-danger',
  };
  return (
    <div className="group relative overflow-hidden rounded-[1.5rem] border border-line bg-surface p-5 shadow-card transition-all duration-300 hover:-translate-y-0.5 hover:shadow-soft">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted">{label}</p>
        <span className={cn('grid size-9 place-items-center rounded-full', tones[tone])}><Icon className="size-4.5" aria-hidden /></span>
      </div>
      {loading ? <Skeleton className="mt-4 h-9 w-24" /> : (
        <p className="mt-3 font-serif text-[2.1rem] leading-none text-forest dark:text-ink">
          {value ?? '—'}{unit && value != null && <span className="ml-1 font-sans text-sm text-faint">{unit}</span>}
        </p>
      )}
      {note && <p className="mt-2 truncate text-xs text-faint">{note}</p>}
    </div>
  );
}

export function Empty({ icon: Icon, title, text, action }) {
  return (
    <div className="relative overflow-hidden rounded-[1.5rem] border border-dashed border-line bg-canvas/60 px-6 py-10 text-center">
      <Botanical name="leafLight" className="-top-4 -right-4 w-20 rotate-45 opacity-30" />
      <span className="mx-auto grid size-12 place-items-center rounded-full bg-sage"><Icon className="size-5 text-leaf" aria-hidden /></span>
      <p className="mt-4 font-serif text-lg text-ink">{title}</p>
      {text && <p className="mx-auto mt-1 max-w-sm text-sm text-muted">{text}</p>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}

export function Pill({ tone = 'muted', children, className }) {
  const tones = {
    muted: 'bg-canvas text-muted border-line', leaf: 'bg-sage text-leaf border-leaf/20', gold: 'bg-gold-soft text-gold border-gold/25',
    danger: 'bg-danger/10 text-danger border-danger/20', warn: 'bg-warn/12 text-warn border-warn/25', sky: 'bg-sky/10 text-sky border-sky/20',
  };
  return <span className={cn('inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[0.7rem] font-medium', tones[tone], className)}>{children}</span>;
}

// ── formatting in the farmer's language ─────────────────────────────────────

export function useFormat() {
  const locale = useLocale();
  const t = useTranslations('dashboard.time');
  const tag = locale === 'en' ? 'en-IN' : `${locale}-IN`;
  const date = (value, opts = { day: 'numeric', month: 'short' }) => {
    if (!value) return '';
    const d = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
    return new Intl.DateTimeFormat(tag, opts).format(d);
  };
  const relativeDay = (value) => {
    if (!value) return '';
    const d = new Date(`${String(value).slice(0, 10)}T00:00:00`);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diff = Math.round((d - today) / 86_400_000);
    if (diff === 0) return t('today');
    if (diff === 1) return t('tomorrow');
    if (diff === -1) return t('yesterday');
    return date(value, { weekday: 'short', day: 'numeric', month: 'short' });
  };
  const number = (n, digits = 0) => (n == null ? '—' : new Intl.NumberFormat(tag, { maximumFractionDigits: digits }).format(n));
  const money = (n) => (n == null ? '—' : new Intl.NumberFormat(tag, { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n));
  const ago = (value) => {
    if (!value) return '';
    const mins = Math.round((Date.now() - new Date(value).getTime()) / 60000);
    if (mins < 60) return t('minutesAgo', { count: Math.max(1, mins) });
    if (mins < 60 * 24) return t('hoursAgo', { count: Math.round(mins / 60) });
    return t('daysAgo', { count: Math.round(mins / 1440) });
  };
  return { date, relativeDay, number, money, ago, locale: tag };
}

/** Days from `from` to today (sowing -> age of the crop). */
export function daysSince(from) {
  if (!from) return null;
  return Math.max(0, Math.floor((Date.now() - new Date(`${String(from).slice(0, 10)}T00:00:00`).getTime()) / 86_400_000));
}

/** A tiny line chart for prices: no library, scales to its box. */
export function Sparkline({ values, className }) {
  const pts = values.filter((v) => v != null);
  if (pts.length < 2) return null;
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const w = 120;
  const h = 36;
  const path = pts.map((v, i) => `${i ? 'L' : 'M'}${((i / (pts.length - 1)) * w).toFixed(1)},${(h - ((v - min) / span) * (h - 4) - 2).toFixed(1)}`).join(' ');
  const up = pts.at(-1) >= pts[0];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={cn('h-9 w-28', className)} aria-hidden>
      <path d={`${path} L${w},${h} L0,${h} Z`} fill={up ? 'var(--fx-leaf)' : 'var(--fx-danger)'} opacity="0.1" />
      <path d={path} fill="none" stroke={up ? 'var(--fx-leaf)' : 'var(--fx-danger)'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

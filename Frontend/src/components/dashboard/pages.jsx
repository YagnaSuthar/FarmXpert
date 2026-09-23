'use client';

// ============================================================
// FILE: src/components/dashboard/pages.jsx
// Tasks, Irrigation, Soil, Market, Usage and Settings.
// ============================================================

import { useMemo, useState } from 'react';
import { useFormatter, useTranslations } from 'next-intl';
import {
  CalendarClock, CheckCircle2, Circle, Cpu, Droplets, Eye, EyeOff, FlaskConical, KeyRound, LogOut, RefreshCw, Search, Sprout, Store,
  Trash2, User, Wifi,
} from '@/components/ui/icons';

import { useRouter } from '@/i18n/navigation';
import { ApiError, api } from '@/lib/api';
import { cn } from '@/lib/cn';
import { useAuth } from '@/context/AuthContext';
import { useFarm } from '@/context/FarmContext';
import { clearApiCache, useApi } from '@/hooks/useApi';
import { ThemeToggle } from '@/components/theme/ThemeProvider';
import {
  Alert, Button, ChoiceChips, Skeleton, TextField, inputClass,
} from '@/components/ui/primitives';
import { Empty, PageHeader, Pill, Section, Sparkline, Stat, useFormat } from './widgets';

const PRIORITY_TONE = { critical: 'danger', high: 'warn', medium: 'gold', low: 'muted', deferred: 'muted' };

function useErr() {
  const e = useTranslations('dashboard.errors');
  return (err) => {
    const code = err instanceof ApiError ? err.code : 'network';
    return e.has(code) ? e(code) : e('generic');
  };
}

// ── tasks ───────────────────────────────────────────────────────────────────

export function TasksPage() {
  const t = useTranslations('dashboard.tasks');
  const p = useTranslations('dashboard.overview.priority');
  const { farm } = useFarm();
  const f = useFormat();
  const [open, setOpen] = useState(true);
  const tasks = useApi(farm ? `/farms/${farm.id}/tasks?open=${open}` : null);

  const groups = useMemo(() => {
    const map = new Map();
    for (const task of tasks.data?.items || []) {
      const key = task.scheduled_date || 'someday';
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(task);
    }
    return [...map.entries()];
  }, [tasks.data]);

  const setStatus = async (task, status) => {
    tasks.mutate((d) => ({ ...d, items: d.items.map((x) => (x.id === task.id ? { ...x, status } : x))
      .filter((x) => !open || ['scheduled', 'delayed'].includes(x.status)) }));
    try { await api.patch(`/tasks/${task.id}`, { status }); } catch { tasks.reload(); }
  };

  return (
    <>
      <PageHeader eyebrow={t('eyebrow')} title={t('title')} script={t('script')} lead={t('lead')}
        action={<ChoiceChips label={t('filter')} value={open ? 'open' : 'all'} onChange={(v) => setOpen(v === 'open')}
          options={[{ value: 'open', label: t('open') }, { value: 'all', label: t('all') }]} />} />
      {tasks.loading ? <Skeleton className="h-64 rounded-[1.75rem]" /> : groups.length === 0 ? (
        <Empty icon={Sprout} title={t('emptyTitle')} text={t('emptyText')}
          action={<Button href="/dashboard" size="sm">{t('makePlan')}</Button>} />
      ) : (
        <div className="space-y-6">
          {groups.map(([day, items]) => (
            <Section key={day} title={day === 'someday' ? t('someday') : f.relativeDay(day)}
              subtitle={day === 'someday' ? null : f.date(day, { weekday: 'long', day: 'numeric', month: 'long' })}>
              <ul className="divide-y divide-line">
                {items.map((task) => {
                  const done = task.status === 'done';
                  return (
                    <li key={task.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-start">
                      <button type="button" onClick={() => setStatus(task, done ? 'scheduled' : 'done')}
                        aria-label={done ? t('undo') : t('done')} className="mt-0.5 shrink-0 text-faint hover:text-leaf">
                        {done ? <CheckCircle2 className="size-5.5 text-leaf" /> : <Circle className="size-5.5" />}
                      </button>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className={cn('font-medium text-ink', done && 'text-faint line-through')}>{task.title}</p>
                          <Pill tone={PRIORITY_TONE[task.priority] || 'muted'}>{p(task.priority)}</Pill>
                          {task.status === 'delayed' && <Pill tone="warn">{t('delayed')}</Pill>}
                        </div>
                        {task.why_now && <p className="mt-1 text-sm leading-relaxed text-muted">{task.why_now}</p>}
                        {task.detail?.do?.length > 0 && (
                          <ul className="mt-2 space-y-1 text-sm text-ink/85">
                            {task.detail.do.slice(0, 4).map((step) => <li key={step} className="flex gap-2"><span className="text-leaf">•</span>{step}</li>)}
                          </ul>
                        )}
                        {task.detail?.safety?.length > 0 && (
                          <p className="mt-2 rounded-xl bg-warn/10 px-3 py-2 text-xs text-warn">{task.detail.safety[0]}</p>
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-2 text-xs text-faint sm:flex-col sm:items-end">
                        {task.scheduled_start_time && <span className="flex items-center gap-1"><CalendarClock className="size-3.5" />{task.scheduled_start_time}</span>}
                        <span>{t('minutes', { count: task.duration_minutes })}</span>
                        {!done && <button type="button" onClick={() => setStatus(task, 'skipped')} className="text-faint underline-offset-2 hover:text-ink hover:underline">{t('skip')}</button>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </Section>
          ))}
        </div>
      )}
    </>
  );
}

// ── irrigation ──────────────────────────────────────────────────────────────

export function IrrigationPage() {
  const t = useTranslations('dashboard.irrigation');
  const o = useTranslations('options');
  const { farm, field } = useFarm();
  const f = useFormat();
  const plans = useApi(farm ? `/farms/${farm.id}/irrigation-plans` : null);
  const items = (plans.data?.items || []).filter((x) => x.status !== 'superseded');

  const record = async (plan, status) => {
    plans.mutate((d) => ({ ...d, items: d.items.map((x) => (x.id === plan.id ? { ...x, status } : x)) }));
    try {
      await api.patch(`/irrigation-plans/${plan.id}`, { status, ...(status === 'applied' && plan.water_depth_mm != null && { applied_depth_mm: plan.water_depth_mm }) });
    } catch { plans.reload(); }
  };

  return (
    <>
      <PageHeader eyebrow={t('eyebrow')} title={t('title')} script={t('script')}
        lead={field?.irrigation_method ? t('lead', { method: o.has(`irrigation.${field.irrigation_method}`) ? o(`irrigation.${field.irrigation_method}`) : field.irrigation_method }) : t('leadNoMethod')} />
      {plans.loading ? <Skeleton className="h-64 rounded-[1.75rem]" /> : items.length === 0 ? (
        <Empty icon={Droplets} title={t('emptyTitle')} text={t('emptyText')}
          action={<Button href={`/dashboard/assistant?q=${encodeURIComponent(t('askQuery'))}`} size="sm">{t('ask')}</Button>} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((plan) => {
            const water = (plan.water_depth_mm || 0) > 0;
            return (
              <article key={plan.id} className={cn('relative overflow-hidden rounded-[1.5rem] border p-5 shadow-card',
                water ? 'border-sky/25 bg-surface' : 'border-line bg-canvas')}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-serif text-xl text-forest dark:text-ink">{f.relativeDay(plan.plan_date)}</p>
                    <p className="text-xs text-faint">{f.date(plan.plan_date, { weekday: 'long', day: 'numeric', month: 'short' })}</p>
                  </div>
                  <span className={cn('grid size-10 place-items-center rounded-full', water ? 'bg-sky/12 text-sky' : 'bg-sage text-leaf')}>
                    <Droplets className="size-5" aria-hidden />
                  </span>
                </div>
                <p className="mt-4 font-serif text-3xl text-ink">
                  {water ? <>{f.number(plan.water_depth_mm, 0)}<span className="ml-1 font-sans text-sm text-faint">mm</span></> : t('noWater')}
                </p>
                {water && plan.duration_hours != null && <p className="mt-1 text-sm text-muted">{t('duration', { hours: f.number(plan.duration_hours, 1) })}</p>}
                {plan.plan?.reason && <p className="mt-2 line-clamp-3 text-sm text-muted">{plan.plan.reason}</p>}
                <div className="mt-4 flex items-center justify-between gap-2">
                  {plan.status === 'planned' ? (
                    <div className="flex gap-2">
                      {water && <Button size="sm" onClick={() => record(plan, 'applied')}>{t('watered')}</Button>}
                      <Button size="sm" variant="ghost" onClick={() => record(plan, 'skipped')}>{t('skipped')}</Button>
                    </div>
                  ) : <Pill tone={plan.status === 'applied' ? 'leaf' : 'muted'}>{t(`status.${plan.status}`)}</Pill>}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </>
  );
}

// ── soil ────────────────────────────────────────────────────────────────────

const SOIL_KEYS = ['soil_moisture', 'soil_ph', 'nitrogen', 'phosphorus', 'potassium', 'electrical_conductivity', 'soil_temperature'];

export function SoilPage() {
  const t = useTranslations('dashboard.soil');
  const sf = useTranslations('onboarding.soilFields');
  const { farm } = useFarm();
  const f = useFormat();
  const err = useErr();
  const history = useApi(farm ? `/farms/${farm.id}/soil?limit=12` : null);
  const devices = useApi(farm ? `/farms/${farm.id}/devices` : null);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ soil_moisture: '', soil_ph: '', nitrogen: '', phosphorus: '', potassium: '' });
  const readings = history.data?.items || [];
  const latest = readings[0];
  const device = (devices.data?.items || []).find((d) => d.is_active);

  const sync = async () => {
    setSyncing(true);
    setMessage(null);
    try {
      await api.post(`/farms/${farm.id}/devices/sync`);
      setMessage({ tone: 'success', text: t('synced') });
      history.reload();
    } catch (e) { setMessage({ tone: 'error', text: err(e) }); } finally { setSyncing(false); }
  };

  const save = async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== '').map(([k, v]) => [k, Number(v)]));
    if (!Object.keys(body).length) return;
    try {
      await api.post(`/farms/${farm.id}/soil`, { ...body, source: 'manual' });
      setAdding(false);
      setForm({ soil_moisture: '', soil_ph: '', nitrogen: '', phosphorus: '', potassium: '' });
      history.reload();
    } catch (e2) { setMessage({ tone: 'error', text: err(e2) }); }
  };

  return (
    <>
      <PageHeader eyebrow={t('eyebrow')} title={t('title')} script={t('script')} lead={t('lead')}
        action={<div className="flex gap-2">
          {device && <Button variant="outline" size="sm" onClick={sync} loading={syncing}><RefreshCw className="size-4" />{t('sync')}</Button>}
          <Button size="sm" onClick={() => setAdding((v) => !v)}><FlaskConical className="size-4" />{t('add')}</Button>
        </div>} />
      {message && <Alert tone={message.tone} className="mb-5">{message.text}</Alert>}
      {adding && (
        <Section title={t('addTitle')} className="mb-6">
          <form onSubmit={save} className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6 lg:items-end">
            {Object.keys(form).map((k) => (
              <TextField key={k} label={sf(k)} inputMode="decimal" value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value.replace(/[^\d.]/g, '') })} />
            ))}
            <Button type="submit" className="lg:mb-0.5">{t('save')}</Button>
          </form>
        </Section>
      )}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {['soil_moisture', 'soil_ph', 'nitrogen', 'potassium'].map((k, i) => (
          <Stat key={k} icon={[Droplets, FlaskConical, Sprout, Sprout][i]} tone={['sky', 'gold', 'leaf', 'leaf'][i]} label={sf(k)}
            loading={history.loading} value={latest?.[k] != null ? f.number(latest[k], k === 'soil_ph' ? 1 : 0) : null}
            unit={k === 'soil_moisture' ? '%' : k === 'soil_ph' ? '' : 'mg/kg'}
            note={latest ? t('from', { source: t(`source.${latest.source}`), when: f.ago(latest.recorded_at) }) : t('none')} />
        ))}
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Section title={t('history')}>
          {history.loading ? <Skeleton className="h-40" /> : !readings.length ? <p className="text-sm text-muted">{t('none')}</p> : (
            <div className="-mx-2 overflow-x-auto">
              <table className="w-full min-w-[34rem] text-sm">
                <thead><tr className="text-left text-xs text-faint">
                  <th className="px-2 py-2 font-medium">{t('when')}</th>
                  {SOIL_KEYS.slice(0, 5).map((k) => <th key={k} className="px-2 py-2 font-medium">{sf(k)}</th>)}
                </tr></thead>
                <tbody className="divide-y divide-line">
                  {readings.map((r) => (
                    <tr key={r.id}>
                      <td className="px-2 py-2.5 text-muted">{f.date(r.recorded_at, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                      {SOIL_KEYS.slice(0, 5).map((k) => <td key={k} className="px-2 py-2.5 text-ink">{r[k] != null ? f.number(r[k], 1) : '—'}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
        <Section title={t('sensor')}>
          {device ? (
            <div className="flex items-start gap-4">
              <span className="grid size-11 place-items-center rounded-full bg-sage"><Wifi className="size-5 text-leaf" /></span>
              <div>
                <p className="font-medium text-ink">{device.label || t('probe')}</p>
                <p className="text-xs text-faint">{t('tokenEnds', { hint: device.token_hint })}</p>
                <p className="mt-1 text-sm text-muted">{device.last_seen_at ? t('lastSeen', { when: f.ago(device.last_seen_at) }) : t('neverSynced')}</p>
              </div>
            </div>
          ) : <Empty icon={Cpu} title={t('noSensor')} text={t('noSensorText')} action={<Button href="/dashboard/settings#device" size="sm">{t('connect')}</Button>} />}
        </Section>
      </div>
    </>
  );
}

// ── market ──────────────────────────────────────────────────────────────────

function MarketView() {
  const t = useTranslations('dashboard.market');
  const o = useTranslations('options');
  const { field, farm } = useFarm();
  const f = useFormat();
  const [commodity, setCommodity] = useState(field?.crop_name || '');
  const [query, setQuery] = useState(field?.crop_name || '');
  const [local, setLocal] = useState(true);
  const path = commodity
    ? `/market/prices?commodity=${encodeURIComponent(commodity)}&days=30&limit=200${local && farm?.state ? `&state=${encodeURIComponent(farm.state)}` : ''}`
    : null;
  const prices = useApi(path);
  const items = prices.data?.items || [];
  const byMarket = useMemo(() => {
    const map = new Map();
    for (const row of items) if (!map.has(row.market)) map.set(row.market, row);
    return [...map.values()].sort((a, b) => (b.modal_price || 0) - (a.modal_price || 0));
  }, [items]);
  const trend = items.slice().reverse().map((r) => r.modal_price);
  const label = (c) => (o.has(`crops.${c.toLowerCase()}`) ? o(`crops.${c.toLowerCase()}`) : c);

  return (
    <>
      <PageHeader eyebrow={t('eyebrow')} title={t('title')} script={t('script')} lead={t('lead')} />
      <form className="mb-6 flex flex-col gap-3 sm:flex-row" onSubmit={(e) => { e.preventDefault(); setCommodity(query.trim()); }}>
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-4 size-4.5 -translate-y-1/2 text-faint" aria-hidden />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('search')} aria-label={t('search')}
            className={cn(inputClass, 'rounded-full pl-11')} />
        </div>
        {farm?.state && <ChoiceChips label={t('area')} value={local ? 'local' : 'india'} onChange={(v) => setLocal(v === 'local')}
          options={[{ value: 'local', label: farm.state }, { value: 'india', label: t('allIndia') }]} />}
        <Button type="submit">{t('show')}</Button>
      </form>
      {!commodity ? <Empty icon={Store} title={t('pickTitle')} text={t('pickText')} />
        : prices.loading ? <Skeleton className="h-64 rounded-[1.75rem]" />
          : !items.length ? <Empty icon={Store} title={t('noneTitle', { crop: label(commodity) })} text={t('noneText')} />
            : (
              <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
                <section className="panel-forest rounded-[1.75rem] p-7 shadow-lift">
                  <div className="pointer-events-none absolute inset-3 rounded-[1.4rem] border border-gold/20" aria-hidden />
                  <p className="relative eyebrow text-gold">{label(commodity)} · {t('last30')}</p>
                  <p className="relative mt-3 font-serif text-5xl text-white">{f.money(prices.data.summary?.modal_avg)}</p>
                  <p className="relative mt-1 text-sm text-white/65">{t('perQuintal')}</p>
                  <div className="relative mt-6 grid grid-cols-2 gap-4 text-sm">
                    <div><p className="text-white/55">{t('low')}</p><p className="font-serif text-2xl text-white">{f.money(prices.data.summary?.modal_min)}</p></div>
                    <div><p className="text-white/55">{t('high')}</p><p className="font-serif text-2xl text-white">{f.money(prices.data.summary?.modal_max)}</p></div>
                  </div>
                  <Sparkline values={trend} className="relative mt-6 h-16 w-full [&_path]:stroke-[var(--fx-gold)]" />
                </section>
                <Section title={t('markets', { count: byMarket.length })}>
                  <ul className="divide-y divide-line">
                    {byMarket.slice(0, 12).map((m, i) => (
                      <li key={m.market} className="flex items-center gap-4 py-3">
                        <span className={cn('grid size-8 shrink-0 place-items-center rounded-full text-xs font-semibold', i === 0 ? 'bg-gold text-forest-deep' : 'bg-canvas text-muted')}>{i + 1}</span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium text-ink">{m.market}</p>
                          <p className="truncate text-xs text-faint">{[m.district, m.state].filter(Boolean).join(', ')} · {f.date(m.arrival_date)}</p>
                        </div>
                        <p className="font-serif text-lg text-forest dark:text-ink">{f.money(m.modal_price)}</p>
                      </li>
                    ))}
                  </ul>
                </Section>
              </div>
            )}
    </>
  );
}

// ── usage ───────────────────────────────────────────────────────────────────

export function UsagePage() {
  const t = useTranslations('dashboard.usage');
  const { user } = useAuth();
  const f = useFormat();
  const usage = useApi(user ? `/users/${user.id}/usage` : null);
  const today = usage.data?.today;
  const pct = today?.limit ? Math.min(100, Math.round((today.used / today.limit) * 100)) : 0;
  const days = useMemo(() => {
    const map = new Map();
    for (const row of usage.data?.days || []) map.set(row.usage_date, (map.get(row.usage_date) || 0) + Number(row.total_tokens || 0));
    return [...map.entries()].sort().slice(-14);
  }, [usage.data]);
  const max = Math.max(1, ...days.map(([, v]) => v));

  return (
    <>
      <PageHeader eyebrow={t('eyebrow')} title={t('title')} script={t('script')} lead={t('lead')} />
      {usage.loading ? <Skeleton className="h-64 rounded-[1.75rem]" /> : (
        <div className="grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
          <Section title={t('today')}>
            <div className="flex flex-col items-center py-4">
              <div className="relative grid size-44 place-items-center">
                <svg viewBox="0 0 120 120" className="absolute inset-0 -rotate-90" aria-hidden>
                  <circle cx="60" cy="60" r="52" fill="none" stroke="var(--fx-line)" strokeWidth="10" />
                  <circle cx="60" cy="60" r="52" fill="none" stroke={pct > 85 ? 'var(--fx-warn)' : 'var(--fx-leaf)'} strokeWidth="10"
                    strokeLinecap="round" strokeDasharray={`${(pct / 100) * 326.7} 326.7`} className="transition-[stroke-dasharray] duration-1000" />
                </svg>
                <div className="text-center">
                  <p className="font-serif text-4xl text-forest dark:text-ink">{100 - pct}%</p>
                  <p className="text-xs text-faint">{t('left')}</p>
                </div>
              </div>
              <p className="mt-4 text-sm text-muted">{today?.limit ? t('used', { used: f.number(today.used), limit: f.number(today.limit) }) : t('unlimited')}</p>
              {today?.voice_seconds_limit && (
                <p className="mt-1 text-xs text-faint">{t('voice', { used: f.number(today.voice_seconds_used / 60, 1), limit: f.number(today.voice_seconds_limit / 60) })}</p>
              )}
              <p className="mt-3 text-xs text-faint">{t('resets')}</p>
            </div>
          </Section>
          <Section title={t('fortnight')} subtitle={t('fortnightNote')}>
            {!days.length ? <p className="text-sm text-muted">{t('none')}</p> : (
              <div className="flex h-48 items-end gap-2 pt-4">
                {days.map(([d, v]) => (
                  <div key={d} className="flex flex-1 flex-col items-center gap-2">
                    <div className="flex h-36 w-full items-end overflow-hidden rounded-lg bg-canvas">
                      <div className="w-full rounded-lg bg-gradient-to-t from-forest to-leaf transition-all duration-700" style={{ height: `${Math.max(4, (v / max) * 100)}%` }} />
                    </div>
                    <span className="text-[0.62rem] text-faint">{f.date(d, { day: 'numeric' })}</span>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>
      )}
    </>
  );
}

// ── settings ────────────────────────────────────────────────────────────────

/** One labelled value in a details grid; empty values show a quiet dash. */
function Detail({ label, children, wide = false }) {
  const empty = children === null || children === undefined || children === '' || (Array.isArray(children) && !children.length);
  return (
    <div className={cn('min-w-0 border-b border-line/70 py-3', wide && 'sm:col-span-2')}>
      <dt className="text-[0.7rem] font-medium tracking-[0.12em] text-faint uppercase">{label}</dt>
      <dd className={cn('mt-1 text-sm break-words', empty ? 'text-faint' : 'text-ink')}>{empty ? '—' : children}</dd>
    </div>
  );
}

/** Everything saved about the farm and its field, read-only. */
function FarmDetails({ farm, field }) {
  const t = useTranslations('dashboard.settings.details');
  const o = useTranslations('options');
  const f = useFormatter();
  const opt = (group, v) => (v && o.has(`${group}.${v}`) ? o(`${group}.${v}`) : v);
  const r = farm.resources || {};
  const date = (d) => (d ? f.dateTime(new Date(d), { day: 'numeric', month: 'short', year: 'numeric' }) : null);
  const coords = farm.latitude != null && farm.longitude != null
    ? `${Number(farm.latitude).toFixed(5)}, ${Number(farm.longitude).toFixed(5)}` : null;
  return (
    <div className="grid gap-8 lg:grid-cols-2">
      <div>
        <p className="mb-1 text-xs font-semibold text-leaf">{t('farm')}</p>
        <dl className="grid gap-x-6 sm:grid-cols-2">
          <Detail label={t('name')}>{farm.name}</Detail>
          <Detail label={t('area')}>{farm.area_acres != null && t('areaValue', { acres: farm.area_acres, ha: farm.area_hectares })}</Detail>
          <Detail label={t('state')}>{farm.state}</Detail>
          <Detail label={t('district')}>{farm.district}</Detail>
          <Detail label={t('address')} wide>{farm.address}</Detail>
          <Detail label={t('location')}>
            {coords && (
              <a className="text-leaf underline-offset-2 hover:underline" target="_blank" rel="noreferrer"
                href={`https://www.google.com/maps?q=${farm.latitude},${farm.longitude}`}>{coords}</a>
            )}
          </Detail>
          <Detail label={t('water')}>{opt('water', farm.water_source)}</Detail>
          <Detail label={t('irrigationAvailable')}>{r.irrigation_available == null ? null : r.irrigation_available ? t('yes') : t('no')}</Detail>
          <Detail label={t('labour')}>{r.labor_units_available}</Detail>
          <Detail label={t('budget')}>{r.budget_available != null && f.number(r.budget_available, { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })}</Detail>
          <Detail label={t('hours')}>{r.working_hours_start && `${r.working_hours_start} – ${r.working_hours_end || ''}`}</Detail>
          <Detail label={t('equipment')} wide>{(r.equipment_available || []).map((e) => opt('equipment', e)).join(', ')}</Detail>
          <Detail label={t('since')}>{date(farm.created_at)}</Detail>
        </dl>
      </div>
      <div>
        <p className="mb-1 text-xs font-semibold text-leaf">{t('field')}</p>
        {field ? (
          <dl className="grid gap-x-6 sm:grid-cols-2">
            <Detail label={t('fieldName')}>{field.name}</Detail>
            <Detail label={t('fieldArea')}>{field.area_acres != null && t('areaValue', { acres: field.area_acres, ha: field.area_hectares })}</Detail>
            <Detail label={t('crop')}>{opt('crops', field.crop_name)}</Detail>
            <Detail label={t('stage')}>{opt('stages', field.growth_stage)}</Detail>
            <Detail label={t('soil')}>{opt('soils', field.soil_type)}</Detail>
            <Detail label={t('irrigation')}>{opt('irrigation', field.irrigation_method)}</Detail>
            <Detail label={t('sown')}>{date(field.sown_on)}</Detail>
            <Detail label={t('harvest')}>{date(field.expected_harvest_on)}</Detail>
          </dl>
        ) : <p className="py-3 text-sm text-faint">{t('noField')}</p>}
      </div>
    </div>
  );
}

/** The connected probe: label, masked token with reveal and copy, last reading time. */
function SavedDevice({ device }) {
  const t = useTranslations('dashboard.settings');
  const f = useFormatter();
  const [shown, setShown] = useState(false);
  const [copied, setCopied] = useState(false);
  if (!device) return <p className="rounded-xl border border-dashed border-line px-4 py-3 text-sm text-faint">{t('noDevice')}</p>;
  const token = device.token || '';
  const masked = token ? `${'•'.repeat(Math.max(0, token.length - 4))}${token.slice(-4)}` : `••••${device.token_hint || ''}`;
  const copy = async () => {
    try { await navigator.clipboard.writeText(token); setCopied(true); setTimeout(() => setCopied(false), 1600); } catch { /* clipboard blocked */ }
  };
  return (
    <div className="rounded-xl border border-line bg-canvas p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-leaf/60" />
            <span className="relative inline-flex size-2 rounded-full bg-leaf" />
          </span>
          <p className="text-sm font-medium text-ink">{device.label || t('probe')}</p>
        </div>
        <p className="text-xs text-faint">
          {device.last_seen_at ? t('lastSeen', { when: f.relativeTime(new Date(device.last_seen_at), new Date()) }) : t('neverSeen')}
        </p>
      </div>
      <div className="mt-3 flex items-center gap-2 rounded-lg border border-line bg-surface py-1.5 pr-1.5 pl-3">
        <code className="min-w-0 flex-1 truncate font-mono text-[0.8rem] tracking-wide text-ink">{shown ? token : masked}</code>
        {token && (
          <>
            <button type="button" onClick={() => setShown((v) => !v)} aria-label={shown ? t('hideToken') : t('showToken')}
              className="grid size-8 place-items-center rounded-md text-faint transition-colors hover:bg-canvas hover:text-ink">
              {shown ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
            <button type="button" onClick={copy}
              className="rounded-md px-2.5 py-1.5 text-xs font-medium text-leaf transition-colors hover:bg-sage">
              {copied ? t('copied') : t('copy')}
            </button>
          </>
        )}
      </div>
      <p className="mt-2 text-xs text-faint">{t('connectedOn', { date: f.dateTime(new Date(device.created_at), { day: 'numeric', month: 'short', year: 'numeric' }) })}</p>
    </div>
  );
}

function SettingsView() {
  const t = useTranslations('dashboard.settings');
  const { user, setUser, logout } = useAuth();
  const { farm, field, reload } = useFarm();
  const router = useRouter();
  const err = useErr();
  const devices = useApi(farm ? `/farms/${farm.id}/devices` : null);
  const device = devices.data?.items?.find((d) => d.is_active) || null;
  const [profile, setProfile] = useState({ name: user?.name || '', phone: user?.phone || '' });
  const [farmForm, setFarmForm] = useState({ name: farm?.name || '', district: farm?.district || '' });
  const [pw, setPw] = useState({ current_password: '', password: '' });
  const [token, setToken] = useState('');
  const [msg, setMsg] = useState({});
  const [busy, setBusy] = useState(null);
  const say = (key, tone, text) => setMsg((m) => ({ ...m, [key]: { tone, text } }));

  const act = async (key, fn, okText) => {
    setBusy(key);
    try { await fn(); if (okText) say(key, 'success', okText); } catch (e) { say(key, 'error', err(e)); } finally { setBusy(null); }
  };

  const signOutEverywhere = async () => {
    await logout({ everywhere: true });
    clearApiCache();
    router.replace('/auth/login');
  };

  return (
    <>
      <PageHeader eyebrow={t('eyebrow')} title={t('title')} script={t('script')} />
      <div className="grid gap-6 xl:grid-cols-2">
        <Section title={t('profile')}>
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); act('profile', async () => {
            const res = await api.patch('/auth/me', { name: profile.name.trim(), ...(profile.phone && { phone: profile.phone.replace(/\s/g, '') }) });
            setUser(res.user);
          }, t('saved')); }}>
            <Alert tone={msg.profile?.tone}>{msg.profile?.text}</Alert>
            <TextField label={t('name')} icon={User} value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
            <TextField label={t('phone')} type="tel" value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} />
            <TextField label={t('email')} value={user?.email || ''} disabled hint={t('emailHint')} />
            <div className="flex items-center justify-between gap-3">
              <ThemeToggle />
              <Button type="submit" loading={busy === 'profile'}>{t('save')}</Button>
            </div>
          </form>
        </Section>

        {farm && (
          <Section title={t('farm')}>
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); act('farm', async () => {
              await api.patch(`/farms/${farm.id}`, { name: farmForm.name.trim(), district: farmForm.district.trim() });
              reload();
            }, t('saved')); }}>
              <Alert tone={msg.farm?.tone}>{msg.farm?.text}</Alert>
              <TextField label={t('farmName')} value={farmForm.name} onChange={(e) => setFarmForm({ ...farmForm, name: e.target.value })} />
              <TextField label={t('district')} value={farmForm.district} onChange={(e) => setFarmForm({ ...farmForm, district: e.target.value })} />
              <p className="text-xs text-faint">{t('farmHint', { acres: farm.area_acres ?? '—' })}</p>
              <div className="flex justify-end"><Button type="submit" loading={busy === 'farm'}>{t('save')}</Button></div>
            </form>
          </Section>
        )}

        {farm && (
          <Section title={t('device')} className="scroll-mt-24" >
            <form id="device" className="space-y-4" onSubmit={(e) => { e.preventDefault(); act('device', async () => {
              await api.post(`/farms/${farm.id}/devices`, { token: token.trim(), label: 'Soil probe' });
              setToken('');
              devices.reload();
            }, t('deviceSaved')); }}>
              <Alert tone={msg.device?.tone}>{msg.device?.text}</Alert>
              <SavedDevice device={device} />
              <TextField label={t('token')} icon={Cpu} value={token} autoComplete="off" spellCheck={false}
                onChange={(e) => setToken(e.target.value.trim())} hint={t('tokenHint')} />
              <div className="flex justify-end"><Button type="submit" disabled={token.length < 8} loading={busy === 'device'}>{t('connect')}</Button></div>
            </form>
          </Section>
        )}

        {farm && (
          <Section title={t('details.title')} className="xl:col-span-2">
            <FarmDetails farm={farm} field={field} />
          </Section>
        )}

        <Section title={t('security')}>
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); act('password', async () => {
            await api.post('/auth/change-password', pw);
            await logout();
            router.replace('/auth/login?reset=1');
          }); }}>
            <Alert tone={msg.password?.tone}>{msg.password?.text}</Alert>
            <TextField label={t('currentPassword')} icon={KeyRound} type="password" autoComplete="current-password"
              value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />
            <TextField label={t('newPassword')} icon={KeyRound} type="password" autoComplete="new-password"
              value={pw.password} onChange={(e) => setPw({ ...pw, password: e.target.value })} hint={t('passwordHint')} />
            <div className="flex flex-wrap justify-between gap-3">
              <Button type="button" variant="ghost" onClick={signOutEverywhere}><LogOut className="size-4" />{t('everywhere')}</Button>
              <Button type="submit" loading={busy === 'password'} disabled={!pw.current_password || !pw.password}>{t('changePassword')}</Button>
            </div>
          </form>
        </Section>

        <Section title={t('danger')} className="border-danger/25 xl:col-span-2">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="max-w-xl text-sm text-muted">{t('deleteText')}</p>
            <Button variant="danger" onClick={() => {
              // eslint-disable-next-line no-alert
              if (!window.confirm(t('deleteConfirm'))) return;
              act('delete', async () => {
                await api.delete(`/users/${user.id}`);
                await logout();
                clearApiCache();
                router.replace('/');
              });
            }} loading={busy === 'delete'}><Trash2 className="size-4" />{t('delete')}</Button>
          </div>
          {msg.delete && <Alert className="mt-4" tone={msg.delete.tone}>{msg.delete.text}</Alert>}
        </Section>
      </div>
    </>
  );
}

// Both seed their forms from the farm: wait for it, and start fresh when the farm changes.
function WhenFarmLoaded({ children }) {
  const { loading } = useFarm();
  return loading ? <Skeleton className="h-72 rounded-[1.75rem]" /> : children;
}
export function MarketPage() {
  const { farm, field } = useFarm();
  return <WhenFarmLoaded><MarketView key={`${farm?.id}:${field?.id}`} /></WhenFarmLoaded>;
}
export function SettingsPage() {
  const { farm } = useFarm();
  return <WhenFarmLoaded><SettingsView key={farm?.id || 'none'} /></WhenFarmLoaded>;
}

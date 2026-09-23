'use client';

// ============================================================
// FILE: src/components/dashboard/Overview.jsx
// The morning screen: what to do today, at a glance.
// ============================================================

import { useEffect, useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import {
  ArrowRight, CalendarDays, CheckCircle2, Circle, CloudSun, Droplets, FlaskConical, Gauge, MapPin, MessageCircle,
  Sparkles, Sprout, Store,
} from '@/components/ui/icons';

import { Link } from '@/i18n/navigation';
import { ApiError, api } from '@/lib/api';
import { cn } from '@/lib/cn';
import { useAuth } from '@/context/AuthContext';
import { useFarm } from '@/context/FarmContext';
import { useApi } from '@/hooks/useApi';
import { askText } from '@/services/api';
import { Alert, Button, Skeleton } from '@/components/ui/primitives';
import { Empty, Pill, Section, Sparkline, Stat, daysSince, useFormat } from './widgets';
import { ThinkingLabel } from './AnswerParts';
import Markdown from './Markdown';

const PRIORITY_TONE = { critical: 'danger', high: 'warn', medium: 'gold', low: 'muted', deferred: 'muted' };

function greetingKey() {
  const h = new Date().getHours();
  return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening';
}

export default function Overview() {
  const t = useTranslations('dashboard.overview');
  const o = useTranslations('options');
  const e = useTranslations('dashboard.errors');
  const locale = useLocale();
  const search = useSearchParams();
  const { user } = useAuth();
  const { farm, field, loading } = useFarm();
  const f = useFormat();
  const fid = farm?.id;

  const tasks = useApi(fid ? `/farms/${fid}/tasks?open=true` : null);
  const irrigation = useApi(fid ? `/farms/${fid}/irrigation-plans` : null);
  const soil = useApi(fid ? `/farms/${fid}/soil/latest` : null);
  const usage = useApi(user ? `/users/${user.id}/usage` : null);
  const crop = field?.crop_name;
  const market = useApi(crop ? `/market/prices?commodity=${encodeURIComponent(crop)}&days=30&limit=60` : null);

  const planKey = fid ? `fx_plan_${fid}_${new Date().toISOString().slice(0, 10)}` : null;
  const [planning, setPlanning] = useState(false);
  const [streaming, setStreaming] = useState(false);
  // today's plan is kept on this device, so coming back to Today shows it instantly
  const [plan, setPlan] = useState(() => {
    try { return planKey ? JSON.parse(localStorage.getItem(planKey)) : null; } catch { return null; }
  });
  const [planError, setPlanError] = useState(null);
  const abort = useRef(null);
  useEffect(() => () => abort.current?.abort(), []);

  const makePlan = async () => {
    setPlanning(true);
    setStreaming(false);
    setPlanError(null);
    setPlan(null);
    abort.current?.abort();
    abort.current = new AbortController();
    let text = '';
    try {
      await askText({ query: t('planQuery'), farmId: fid, fieldId: field?.id, intents: ['daily_plan'], language: locale },
        (event, data) => {
          if (event === 'delta') {
            text += data.text;
            setStreaming(true);
            setPlan({ text, at: null });
          } else if (event === 'done') {
            const done = { text: data.answer || text || data.summary || '', at: new Date().toISOString() };
            setPlan(done);
            try { localStorage.setItem(planKey, JSON.stringify(done)); } catch { /* storage full or blocked */ }
          } else if (event === 'error') {
            const code = data?.code || 'generic';
            setPlanError(e.has(code) ? e(code) : e('generic'));
          }
        }, abort.current.signal);
      tasks.reload();
      irrigation.reload();
    } catch (err) {
      if (err?.name === 'AbortError') return;
      const code = err instanceof ApiError ? err.code : 'network';
      setPlanError(e.has(code) ? e(code) : e('generic'));
    } finally {
      setPlanning(false);
      setStreaming(false);
    }
  };

  const firstName = (user?.name || '').split(/\s+/)[0];
  const age = daysSince(field?.sown_on);
  const reading = soil.data;
  const nextWater = (irrigation.data?.items || []).filter((p) => p.status === 'planned')
    .sort((a, b) => a.plan_date.localeCompare(b.plan_date))[0];
  const openTasks = tasks.data?.items || [];
  const prices = (market.data?.items || []).slice().reverse();
  const today = usage.data?.today;
  const allowance = today?.limit ? Math.max(0, Math.round((1 - today.used / today.limit) * 100)) : null;

  if (loading && !farm) return <OverviewSkeleton />;

  return (
    <div className="space-y-6 animate-rise">
      {search.get('welcome') && <Alert tone="success">{t('welcome')}</Alert>}

      {/* ── hero ─────────────────────────────────────────────── */}
      <section className="panel-forest rounded-2xl p-7 sm:p-9">
        <div className="relative grid gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] lg:items-end">
          <div>
            <p className="eyebrow text-gold/90">{f.date(new Date(), { weekday: 'long', day: 'numeric', month: 'long' })}</p>
            <h1 className="mt-3 text-[2.1rem] leading-tight text-white sm:text-5xl">
              {t(`greeting.${greetingKey()}`)},{' '}
              <span className="font-script text-[2.8rem] font-normal text-gold sm:text-6xl">{firstName}</span>
            </h1>
            <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-white/70">
              {farm && <span className="flex items-center gap-1.5"><MapPin className="size-4 text-gold/80" aria-hidden />{farm.name}{farm.district ? ` · ${farm.district}` : ''}</span>}
              {crop && (
                <span className="flex items-center gap-1.5">
                  <Sprout className="size-4 text-gold/80" aria-hidden />
                  {o.has(`crops.${crop}`) ? o(`crops.${crop}`) : crop}
                  {field?.growth_stage && ` · ${o.has(`stages.${field.growth_stage}`) ? o(`stages.${field.growth_stage}`) : field.growth_stage}`}
                  {age != null && ` · ${t('dayOfCrop', { day: age })}`}
                </span>
              )}
            </div>
          </div>
          <div className="rounded-[1.4rem] border border-panel-line bg-panel-raised p-5 shadow-raised">
            {planning && !streaming ? (
              <>
                <p className="flex items-center gap-2 text-xs font-medium tracking-wide text-gold uppercase"><Sparkles className="size-3.5" />{t('todaysPlan')}</p>
                <div className="mt-3 [&_.fx-thinking-text]:[--fx-muted:rgb(255_255_255/0.55)] [&_.fx-thinking-text]:[--fx-ink:#fff]"><ThinkingLabel /></div>
              </>
            ) : plan?.text ? (
              <>
                <p className="flex items-center justify-between gap-2 text-xs font-medium tracking-wide text-gold uppercase">
                  <span className="flex items-center gap-2"><Sparkles className="size-3.5" />{t('todaysPlan')}</span>
                  {plan.at && <span className="font-normal tracking-normal text-white/45 normal-case">{t('planUpdated', { time: f.date(plan.at, { hour: 'numeric', minute: '2-digit' }) })}</span>}
                </p>
                <div className="fx-plan mt-2 max-h-56 overflow-y-auto pr-1 text-sm no-scrollbar">
                  <Markdown text={plan.text} caret={streaming} />
                </div>
              </>
            ) : (
              <>
                <p className="font-serif text-lg text-white">{t('planTitle')}</p>
                <p className="mt-1 text-sm text-white/65">{t('planLead')}</p>
              </>
            )}
            {planError && <p className="mt-3 text-xs text-[#f7b4b4]">{planError}</p>}
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="gold" size="sm" onClick={makePlan} loading={planning}>
                <Sparkles className="size-4" aria-hidden />{plan ? t('planAgain') : t('planButton')}
              </Button>
              <Button href="/dashboard/assistant" variant="light" size="sm" className="border border-panel-line bg-transparent text-white hover:bg-panel-line">
                <MessageCircle className="size-4" aria-hidden />{t('ask')}
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* ── key numbers ──────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat icon={Droplets} tone="sky" label={t('stats.moisture')} loading={soil.loading}
          value={reading?.soil_moisture != null ? f.number(reading.soil_moisture, 0) : null} unit="%"
          note={reading ? t('stats.measured', { when: f.ago(reading.recorded_at) }) : t('stats.noReading')} />
        <Stat icon={FlaskConical} tone="gold" label={t('stats.ph')} loading={soil.loading}
          value={reading?.soil_ph != null ? f.number(reading.soil_ph, 1) : null}
          note={reading?.soil_ph != null ? t(`stats.phBand.${reading.soil_ph < 6 ? 'acid' : reading.soil_ph > 7.8 ? 'alkaline' : 'good'}`) : t('stats.noReading')} />
        <Stat icon={CalendarDays} tone="leaf" label={t('stats.nextWater')} loading={irrigation.loading}
          value={nextWater ? f.relativeDay(nextWater.plan_date) : null}
          note={nextWater?.water_depth_mm != null ? t('stats.depth', { mm: f.number(nextWater.water_depth_mm, 0) }) : t('stats.noPlan')} />
        <Stat icon={Gauge} tone={allowance != null && allowance < 20 ? 'warn' : 'leaf'} label={t('stats.allowance')} loading={usage.loading}
          value={allowance != null ? `${allowance}%` : null} note={t('stats.allowanceNote')} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        {/* ── today's work ───────────────────────────────────── */}
        <Section title={t('tasks.title')} subtitle={t('tasks.subtitle', { count: openTasks.length })}
          href="/dashboard/tasks" linkLabel={t('seeAll')}>
          {tasks.loading ? <ListSkeleton /> : openTasks.length === 0 ? (
            <Empty icon={Sprout} title={t('tasks.emptyTitle')} text={t('tasks.emptyText')}
              action={<Button size="sm" onClick={makePlan} loading={planning}>{t('planButton')}</Button>} />
          ) : (
            <ul className="divide-y divide-line">
              {openTasks.slice(0, 5).map((task) => (
                <TaskRow key={task.id} task={task} onDone={async () => {
                  tasks.mutate((d) => ({ ...d, items: d.items.filter((x) => x.id !== task.id) }));
                  try { await api.patch(`/tasks/${task.id}`, { status: 'done' }); } catch { tasks.reload(); }
                }} />
              ))}
            </ul>
          )}
        </Section>

        <div className="space-y-6">
          {/* ── water ──────────────────────────────────────── */}
          <Section title={t('water.title')} href="/dashboard/irrigation" linkLabel={t('seeAll')}>
            {irrigation.loading ? <ListSkeleton rows={3} /> : !(irrigation.data?.items || []).length ? (
              <Empty icon={Droplets} title={t('water.emptyTitle')} text={t('water.emptyText')} />
            ) : (
              <WaterStrip plans={irrigation.data.items} />
            )}
          </Section>

          {/* ── market ─────────────────────────────────────── */}
          <Section title={t('market.title', { crop: crop ? (o.has(`crops.${crop}`) ? o(`crops.${crop}`) : crop) : '' })}
            href="/dashboard/market" linkLabel={t('seeAll')}>
            {!crop ? <p className="text-sm text-muted">{t('market.noCrop')}</p>
              : market.loading ? <Skeleton className="h-16" />
                : market.data?.summary ? (
                  <div className="flex items-end justify-between gap-4">
                    <div>
                      <p className="font-serif text-3xl text-forest dark:text-ink">{f.money(market.data.summary.modal_avg)}</p>
                      <p className="mt-1 text-xs text-faint">{t('market.perQuintal', { count: market.data.summary.observations })}</p>
                    </div>
                    <Sparkline values={prices.map((p) => p.modal_price)} />
                  </div>
                ) : <p className="text-sm text-muted">{t('market.none')}</p>}
          </Section>
        </div>
      </div>

      {/* ── ask ──────────────────────────────────────────────── */}
      <Section title={t('quick.title')} subtitle={t('quick.subtitle')}>
        <div className="flex flex-wrap gap-2">
          {['water', 'fertiliser', 'weather', 'pest', 'sell'].map((q) => (
            <Link key={q} href={`/dashboard/assistant?q=${encodeURIComponent(t(`quick.q.${q}`))}`}
              className="inline-flex items-center gap-2 rounded-[3px] border border-line bg-canvas px-4 py-2 text-sm text-ink transition-all hover:-translate-y-0.5 hover:border-leaf/50 hover:shadow-card">
              {{ water: <Droplets className="size-4 text-sky" />, fertiliser: <FlaskConical className="size-4 text-gold" />,
                weather: <CloudSun className="size-4 text-warn" />, pest: <Sprout className="size-4 text-leaf" />,
                sell: <Store className="size-4 text-forest dark:text-leaf" /> }[q]}
              {t(`quick.q.${q}`)}
              <ArrowRight className="size-3.5 text-faint" aria-hidden />
            </Link>
          ))}
        </div>
      </Section>
    </div>
  );
}

function TaskRow({ task, onDone }) {
  const t = useTranslations('dashboard.overview');
  const f = useFormat();
  const [done, setDone] = useState(false);
  return (
    <li className="flex items-start gap-3 py-3.5">
      <button type="button" onClick={() => { setDone(true); onDone(); }} aria-label={t('tasks.markDone')}
        className="mt-0.5 shrink-0 text-faint transition-colors hover:text-leaf">
        {done ? <CheckCircle2 className="size-5 text-leaf" /> : <Circle className="size-5" />}
      </button>
      <div className="min-w-0 flex-1">
        <p className={cn('text-[0.95rem] leading-snug text-ink', done && 'text-faint line-through')}>{task.title}</p>
        {task.why_now && <p className="mt-0.5 line-clamp-2 text-xs text-muted">{task.why_now}</p>}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        <Pill tone={PRIORITY_TONE[task.priority] || 'muted'}>{t(`priority.${task.priority}`)}</Pill>
        {task.scheduled_date && (
          <span className="text-[0.7rem] text-faint">{f.relativeDay(task.scheduled_date)}{task.scheduled_start_time ? ` · ${task.scheduled_start_time}` : ''}</span>
        )}
      </div>
    </li>
  );
}

function WaterStrip({ plans }) {
  const t = useTranslations('dashboard.overview');
  const f = useFormat();
  const days = plans.filter((p) => p.status !== 'superseded')
    .sort((a, b) => a.plan_date.localeCompare(b.plan_date)).slice(-7);
  const max = Math.max(1, ...days.map((d) => d.water_depth_mm || 0));
  return (
    <div className="flex items-end justify-between gap-2 pt-2" role="list">
      {days.map((d) => {
        const water = (d.water_depth_mm || 0) > 0;
        return (
          <div key={d.id} role="listitem" className="flex flex-1 flex-col items-center gap-2"
            aria-label={`${f.relativeDay(d.plan_date)}: ${water ? t('water.mm', { mm: f.number(d.water_depth_mm, 0) }) : t('water.none')}`}>
            <span className="text-[0.65rem] text-faint">{water ? f.number(d.water_depth_mm, 0) : '·'}</span>
            <div className="flex h-20 w-full max-w-9 items-end overflow-hidden rounded-full bg-sage">
              <div className={cn('w-full rounded-full transition-all duration-700', d.status === 'applied' ? 'bg-leaf' : 'bg-gradient-to-t from-sky to-sky/60')}
                style={{ height: `${water ? Math.max(12, (d.water_depth_mm / max) * 100) : 6}%` }} />
            </div>
            <span className="text-[0.68rem] text-muted">{f.date(d.plan_date, { weekday: 'short' })}</span>
          </div>
        );
      })}
    </div>
  );
}

function ListSkeleton({ rows = 4 }) {
  return <div className="space-y-3">{Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-12" />)}</div>;
}

function OverviewSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-52 rounded-[2rem]" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-32 rounded-[4px]" />)}</div>
      <Skeleton className="h-72 rounded-[4px]" />
    </div>
  );
}


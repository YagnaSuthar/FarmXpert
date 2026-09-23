'use client';

// ============================================================
// FILE: src/components/dashboard/AgentPicker.jsx
//
// Who answers: "FarmXpert (all experts)" lets the orchestrator decide;
// or the farmer talks to one expert agent directly. A compact trigger
// in the composer opens a menu upward (the composer sits at the bottom):
// icon, name and a one-line description per agent, a check on the
// current one. Closes on outside click and Escape; arrow keys move.
// ============================================================

import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { cn } from '@/lib/cn';
import { Check, ChevronsUpDown, Sparkles } from '@/components/ui/icons';
import { AGENTS } from './AnswerParts';

export const AGENT_CHOICES = ['auto', 'weather_watcher', 'soil_health', 'irrigation_planner', 'crop_predictor',
  'task_scheduler', 'market_intelligence'];

function AgentIcon({ name, className }) {
  const meta = name === 'auto' ? { icon: Sparkles, tone: 'text-gold' } : AGENTS[name];
  return <meta.icon className={cn(meta.tone, className)} aria-hidden />;
}

export default function AgentPicker({ value, onChange, farmName, placement = 'up' }) {
  const t = useTranslations('dashboard.assistant.picker');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef(null);
  const items = useRef([]);

  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (!root.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('pointerdown', away);
    return () => document.removeEventListener('pointerdown', away);
  }, [open]);

  useEffect(() => { if (open) items.current[active]?.focus(); }, [open, active]);

  const toggle = () => {
    setActive(Math.max(0, AGENT_CHOICES.indexOf(value)));
    setOpen((o) => !o);
  };
  const choose = (name) => { onChange(name); setOpen(false); };
  const onKey = (e) => {
    if (e.key === 'Escape') { setOpen(false); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => (i + 1) % AGENT_CHOICES.length); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => (i - 1 + AGENT_CHOICES.length) % AGENT_CHOICES.length); }
  };

  return (
    <div ref={root} className="relative" onKeyDown={onKey}>
      <button type="button" onClick={toggle} aria-haspopup="listbox" aria-expanded={open}
        className={cn('group inline-flex max-w-full items-center gap-2 rounded-full border py-1 pr-2 pl-1.5 text-xs transition-all',
          open ? 'border-leaf/40 bg-canvas text-ink' : 'border-transparent text-muted hover:border-line hover:bg-canvas hover:text-ink')}>
        <AgentIcon name={value} className="size-4 shrink-0" />
        <span className="truncate font-medium">{t(`${value}.name`)}</span>
        {value === 'auto' && farmName && <span className="hidden truncate text-faint sm:inline">· {farmName}</span>}
        <ChevronsUpDown className="size-3.5 shrink-0 text-faint" />
      </button>

      {open && (
        <div role="listbox" aria-label={t('label')}
          className={cn('absolute left-0 z-30 w-[18.5rem] overflow-hidden rounded-2xl border border-line/80 bg-surface p-1.5',
            'shadow-[0_24px_48px_-20px_rgb(0_0_0/0.35),0_2px_6px_rgb(0_0_0/0.05)] animate-rise',
            placement === 'up' ? 'bottom-full mb-2' : 'top-full mt-2')}>
          <p className="px-2.5 pt-1.5 pb-2 text-[0.65rem] font-medium tracking-[0.14em] text-faint uppercase">{t('label')}</p>
          {AGENT_CHOICES.map((name, i) => {
            const selected = value === name;
            return (
              <div key={name}>
              {i === 1 && <div className="mx-2.5 my-1.5 h-px bg-line" aria-hidden />}
              <button ref={(el) => { items.current[i] = el; }} type="button" role="option" aria-selected={selected}
                onClick={() => choose(name)} onMouseEnter={() => setActive(i)}
                className={cn('flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-left outline-none transition-colors',
                  selected ? 'bg-sage/70' : i === active ? 'bg-canvas' : '')}>
                <span className="grid size-7 shrink-0 place-items-center">
                  <AgentIcon name={name} className="size-[1.2rem]" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[0.82rem] leading-tight font-medium text-ink">{t(`${name}.name`)}</span>
                  <span className="mt-0.5 block truncate text-[0.72rem] leading-snug text-muted">{t(`${name}.about`)}</span>
                </span>
                {selected && <Check className="size-4 shrink-0 text-leaf" strokeWidth={2.2} />}
              </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

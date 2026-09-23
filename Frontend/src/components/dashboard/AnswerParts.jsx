'use client';

// ============================================================
// FILE: src/components/dashboard/AnswerParts.jsx
//
// The pieces of an assistant answer:
//   <ThinkingLabel>  shimmering status line that keeps changing, in
//                    a shuffled order, while the agents work
//   <RevealText>     the answer written out smoothly, word by word,
//                    however bursty the stream is, as Markdown
//   <AgentCredits>   which expert agents the answer came from
// ============================================================

import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { BookOpen, CalendarCheck, CloudSun, Droplets, Sprout, TrendingUp, Wheat, Sparkles } from '@/components/ui/icons';

import Markdown from './Markdown';

const THINKING_KEYS = ['reading', 'weather', 'soil', 'water', 'crop', 'market', 'history', 'compare',
  'doses', 'season', 'checking', 'writing'];

function shuffled(list, avoidFirst) {
  const a = [...list];
  for (let i = a.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  if (a[0] === avoidFirst && a.length > 1) [a[0], a[1]] = [a[1], a[0]];
  return a;
}

/** A status line that never repeats itself back to back, with a light sweeping through it. */
export function ThinkingLabel() {
  const t = useTranslations('dashboard.assistant.thinkingSteps');
  const [state, setState] = useState(() => ({ order: shuffled(THINKING_KEYS), index: 0 }));

  useEffect(() => {
    const id = setInterval(() => {
      setState(({ order, index }) => (index + 1 < order.length
        ? { order, index: index + 1 }
        : { order: shuffled(THINKING_KEYS, order[order.length - 1]), index: 0 }));
    }, 2300);
    return () => clearInterval(id);
  }, []);

  const key = state.order[state.index];
  return (
    <span className="flex items-center gap-2.5 py-0.5" role="status">
      <span className="fx-orb" aria-hidden />
      <span key={key} className="fx-thinking-text text-[0.95rem] font-medium">{t(key)}</span>
    </span>
  );
}

/**
 * Writes `text` out smoothly. The stream arrives in bursts; this releases
 * characters at a pace that catches up with the backlog (faster when far
 * behind), so it reads like a steady hand writing rather than jumps.
 */
export function RevealText({ text, streaming, onGrow }) {
  const [shown, setShown] = useState(0);
  const target = useRef(text);
  useEffect(() => { target.current = text; }, [text]);

  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    const tick = (now) => {
      const dt = Math.min(64, now - last);
      last = now;
      setShown((n) => {
        const goal = target.current.length;
        if (n >= goal) return n;
        const backlog = goal - n;
        const speed = 55 + backlog * 2.2;                  // chars per second
        let next = Math.min(goal, n + Math.max(1, Math.round((speed * dt) / 1000)));
        // finish the current word, so words land whole
        while (next < goal && /\S/.test(target.current[next]) && next - n < 14) next += 1;
        return next;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => { onGrow?.(); }, [shown, onGrow]);

  const writing = streaming || shown < text.length;
  return <Markdown text={text.slice(0, shown)} caret={writing} />;
}

export const AGENTS = {
  weather_watcher: { icon: CloudSun, tone: 'text-sky' },
  soil_health: { icon: Sprout, tone: 'text-leaf' },
  irrigation_planner: { icon: Droplets, tone: 'text-sky' },
  crop_predictor: { icon: Wheat, tone: 'text-gold' },
  task_scheduler: { icon: CalendarCheck, tone: 'text-leaf' },
  market_intelligence: { icon: TrendingUp, tone: 'text-gold' },
  retrieval_agent: { icon: BookOpen, tone: 'text-muted' },
};

/** "Answered by" chips for the agents that contributed. */
export function AgentCredits({ agents }) {
  const t = useTranslations('dashboard.assistant');
  if (!agents?.length) return null;
  return (
    <div className="mt-4 flex flex-wrap items-center gap-1.5 border-t border-line/70 pt-3 animate-rise">
      <span className="mr-1 text-[0.7rem] font-medium tracking-[0.14em] text-faint uppercase">{t('answeredBy')}</span>
      {agents.map((name) => {
        const meta = AGENTS[name] || { icon: Sparkles, tone: 'text-leaf' };
        const label = t.has(`agents.${name}`) ? t(`agents.${name}`)
          : name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
        return (
          <span key={name}
            className="inline-flex items-center gap-1.5 rounded-full border border-line bg-canvas px-2.5 py-1 text-xs text-ink/85">
            <meta.icon className={`size-3.5 ${meta.tone}`} aria-hidden />{label}
          </span>
        );
      })}
    </div>
  );
}

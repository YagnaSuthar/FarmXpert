'use client';

// ============================================================
// FILE: src/components/dashboard/WelcomeIntro.jsx
//
// The first-time greeting, shown once per farmer on this device the
// first time they reach the dashboard - in the spirit of a new phone
// saying "hello": greetings in India's languages are written out with
// a gold pen one after another, the farmer is welcomed by name letter
// by letter, and the intro lifts away as the dashboard settles in.
//
// The cover is decided on the very first render, so the dashboard is
// never seen before the intro. Every step is CSS (transform, opacity,
// stroke, filter), so it stays smooth on low-end phones.
// Skippable at any moment; skipped entirely for reduced motion.
// ============================================================

import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslations } from 'next-intl';

const HELLOS = [
  { text: 'hello', lang: 'en', script: true },
  { text: 'नमस्ते', lang: 'hi' },
  { text: 'નમસ્તે', lang: 'gu' },
  { text: 'வணக்கம்', lang: 'ta' },
  { text: 'నమస్కారం', lang: 'te' },
  { text: 'ਸਤ ਸ੍ਰੀ ਅਕਾਲ', lang: 'pa' },
  { text: 'নমস্কার', lang: 'bn' },
  { text: 'ನಮಸ್ಕಾರ', lang: 'kn' },
];
const BREATH_MS = 600;                          // a moment of darkness before the pen moves
const FIRST_MS = 3400;                          // the first "hello" is drawn slowly
const HELLO_MS = 1500;
const NAME_AT = BREATH_MS + FIRST_MS + (HELLOS.length - 1) * HELLO_MS;
const OPEN_AT = NAME_AT + 3200;
const END_AT = OPEN_AT + 1100;

const storageKey = (userId) => `fx_welcomed_${userId}`;

function seen(userId) {
  try { return window.localStorage.getItem(storageKey(userId)) === '1'; } catch { return true; }
}
function markSeen(userId) {
  try { window.localStorage.setItem(storageKey(userId), '1'); } catch { /* private mode: fine */ }
}
function wanted(user) {
  return Boolean(user?.id) && !seen(user.id)
    && !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export default function WelcomeIntro({ user }) {
  const t = useTranslations('dashboard.intro');
  // This component only mounts in the browser (behind RequireAuth), so the
  // choice can be made on the first render: the dark cover paints together
  // with the dashboard, never after it.
  const [phase, setPhase] = useState(() => ({ step: wanted(user) ? 'cover' : 'idle', hello: 0 }));

  const finish = useCallback(() => {
    markSeen(user.id);
    setPhase((p) => ({ ...p, step: 'done' }));
    setTimeout(() => { delete document.documentElement.dataset.introReveal; }, 1500);
  }, [user.id]);

  useEffect(() => {
    if (phase.step !== 'cover') return undefined;
    const html = document.documentElement;
    const timers = [];
    const at = (ms, fn) => timers.push(setTimeout(fn, ms));
    at(BREATH_MS, () => setPhase({ step: 'hello', hello: 0 }));
    HELLOS.slice(1).forEach((_, i) => at(BREATH_MS + FIRST_MS + i * HELLO_MS, () => setPhase({ step: 'hello', hello: i + 1 })));
    at(NAME_AT, () => setPhase((p) => ({ ...p, step: 'name' })));
    at(OPEN_AT, () => {
      html.dataset.introReveal = '1';               // the dashboard settles in underneath
      setPhase((p) => ({ ...p, step: 'open' }));
    });
    at(END_AT, finish);
    const before = html.style.overflow;
    html.style.overflow = 'hidden';
    return () => { timers.forEach(clearTimeout); html.style.overflow = before; };
    // runs once, when the cover first appears
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (phase.step === 'done') document.documentElement.style.overflow = '';
  }, [phase.step]);

  if (phase.step === 'idle' || phase.step === 'done') return null;
  const hello = HELLOS[phase.hello];
  const firstName = (user?.name || '').split(/\s+/)[0];
  const welcome = firstName ? t('welcomeName', { name: firstName }) : t('welcome');

  return createPortal(
    <div className={`fx-intro${phase.step === 'open' ? ' is-opening' : ''}`} role="dialog" aria-label={t('label')}>
      <div className="fx-intro-glow fx-intro-glow-a" aria-hidden />
      <div className="fx-intro-glow fx-intro-glow-b" aria-hidden />
      <div className="fx-intro-halo" aria-hidden />
      <div className="fx-intro-grain" aria-hidden />
      <div className="fx-intro-vignette" aria-hidden />

      <div className="fx-intro-stage">
        {phase.step === 'hello' && (
          // Written, not faded: a glowing gold pen traces the outline, the
          // ivory ink floods in under a moving sheen, then it lifts away.
          <svg key={phase.hello} lang={hello.lang} viewBox="0 0 1200 360" role="img" aria-label={hello.text}
            className={`fx-intro-hello${hello.script ? ' is-script' : ''}${phase.hello === 0 ? ' is-first' : ''}`}>
            <defs>
              <linearGradient id="fxHelloInk" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="#f4f1e8" />
                <stop offset="45%" stopColor="#f4f1e8" />
                <stop offset="62%" stopColor="#f3d98f" />
                <stop offset="72%" stopColor="#f4f1e8" />
                <stop offset="100%" stopColor="#f4f1e8" />
                <animateTransform attributeName="gradientTransform" type="translate" from="-0.7 0" to="0.35 0"
                  dur={phase.hello === 0 ? '3.4s' : '1.5s'} fill="freeze" />
              </linearGradient>
            </defs>
            <text x="50%" y="56%" textAnchor="middle" dominantBaseline="middle">{hello.text}</text>
          </svg>
        )}
        {(phase.step === 'name' || phase.step === 'open') && (
          <div className="fx-intro-welcome">
            <svg className="fx-intro-sprout" viewBox="0 0 64 64" aria-hidden>
              <path d="M32 58 C32 44 32 36 32 26" />
              <path d="M32 36 C22 36 14 30 12 18 C24 18 32 24 32 36 Z" />
              <path d="M32 30 C40 30 48 25 51 14 C40 14 33 20 32 30 Z" />
            </svg>
            <p className="fx-intro-kicker">{t('kicker')}</p>
            <h1 className="fx-intro-name" aria-label={welcome}>
              {Array.from(welcome).map((ch, i) => (
                <span key={i} aria-hidden style={{ animationDelay: `${0.55 + i * 0.045}s` }}>{ch === ' ' ? ' ' : ch}</span>
              ))}
            </h1>
            <span className="fx-intro-rule" aria-hidden />
            <p className="fx-intro-line">{t('line')}</p>
          </div>
        )}
      </div>

      <span className="fx-intro-progress" style={{ animationDuration: `${END_AT}ms` }} aria-hidden />
      <button type="button" className="fx-intro-skip" onClick={finish}>{t('skip')}</button>
    </div>,
    document.body.querySelector('.fx-app') || document.body,
  );
}

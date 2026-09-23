'use client';

// ============================================================
// FILE: src/components/dashboard/VoiceMode.jsx
//
// Voice mode: a full-screen, floating conversation - in the spirit of
// ChatGPT's voice mode. One living orb says what is happening:
//   idle      breathing slowly             "Tap to talk"
//   listening swells with your voice       live mic level
//   thinking  slow swirl                   agents at work
//   speaking  pulses with the answer       sentence captions
//
// Hands-free: tap once and talk. A pause (silence after speech) sends
// the question; the answer is spoken sentence by sentence; then it
// listens again. Tap the orb or the mic to stop, X to leave.
// ============================================================

import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';

import { cn } from '@/lib/cn';
import { useRouter } from '@/i18n/navigation';
import { useFarm } from '@/context/FarmContext';
import useAudioQueue from '@/hooks/useAudioQueue';
import useVoiceRecorder from '@/hooks/useVoiceRecorder';
import { ApiError, askVoice } from '@/services/api';
import { Mic, Square } from '@/components/ui/icons';

const SPEECH_LEVEL = 0.12;     // above this, the farmer is talking
const SILENCE_MS = 1300;       // this long quiet after talking = question finished
const NO_SPEECH_MS = 8000;     // nothing said at all: stop listening

export default function VoiceMode() {
  const t = useTranslations('dashboard.voice');
  const ta = useTranslations('dashboard.assistant');
  const locale = useLocale();
  const router = useRouter();
  const { farm, field } = useFarm();
  const farmId = farm?.id;
  const fieldId = field?.id;
  const recorder = useVoiceRecorder();
  const player = useAudioQueue();

  const [phase, setPhase] = useState('idle');         // idle | listening | thinking | speaking
  const [heard, setHeard] = useState('');             // the farmer's words
  const [answer, setAnswer] = useState('');           // what is being said
  const [error, setError] = useState(null);
  const [handsFree, setHandsFree] = useState(true);

  const conversationId = useRef(null);
  const abort = useRef(null);
  const vad = useRef({ spoke: false, quietSince: 0, startedAt: 0 });
  const answered = useRef(false);

  const errorText = useCallback((code) => (ta.has(`errors.${code}`) ? ta(`errors.${code}`) : ta('errors.generic')), [ta]);

  // ── listen ──────────────────────────────────────────────────────────────
  const listen = useCallback(async () => {
    player.stop();
    abort.current?.abort();
    setError(null);
    setAnswer('');
    vad.current = { spoke: false, quietSince: 0, startedAt: performance.now() };
    await recorder.start();
    setPhase('listening');
  }, [player, recorder]);

  const send = useCallback(async () => {
    const recording = await recorder.stop();
    if (!recording) { setPhase('idle'); return; }
    setPhase('thinking');
    setHeard('');
    answered.current = false;
    abort.current = new AbortController();
    try {
      await askVoice(recording, { farmId, fieldId, conversationId: conversationId.current, language: locale },
        (event, data) => {
          if (event === 'conversation') conversationId.current = data.conversation_id;
          else if (event === 'transcript') setHeard(data.text);
          else if (event === 'delta') setAnswer((a) => a + data.text);
          else if (event === 'audio') { player.enqueue(data); setPhase('speaking'); }
          else if (event === 'done') {
            answered.current = true;
            setAnswer((a) => a || data.answer || data.summary || '');
          } else if (event === 'error') { setError(errorText(data.code)); setPhase('idle'); }
        }, abort.current.signal);
    } catch (err) {
      if (err?.name === 'AbortError') return;
      setError(errorText(err instanceof ApiError ? err.code : 'network'));
      setPhase('idle');
    }
  }, [recorder, farmId, fieldId, locale, player, errorText]);

  // ── voice activity: a pause after speaking sends the question ───────────
  // Checked on a steady timer (not on level changes), so dead silence -
  // a level that never changes - still counts as the pause that sends.
  const levelNow = useRef(0);
  useEffect(() => { levelNow.current = recorder.level; }, [recorder.level]);
  useEffect(() => {
    if (phase !== 'listening') return undefined;
    const id = setInterval(() => {
      const now = performance.now();
      const v = vad.current;
      if (levelNow.current > SPEECH_LEVEL) { v.spoke = true; v.quietSince = 0; return; }
      if (!v.spoke) {
        if (now - v.startedAt > NO_SPEECH_MS) { clearInterval(id); recorder.cancel(); setPhase('idle'); setError(t('noSpeech')); }
        return;
      }
      if (!v.quietSince) v.quietSince = now;
      else if (now - v.quietSince > SILENCE_MS) { clearInterval(id); send(); }
    }, 100);
    return () => clearInterval(id);
  }, [phase, send, recorder, t]);

  // ── when the answer has been spoken: listen again (hands-free) ──────────
  useEffect(() => {
    if (phase === 'speaking' && !player.speaking && answered.current) {
      const id = setTimeout(() => {
        if (handsFree) listen(); else setPhase('idle');
      }, 450);
      return () => clearTimeout(id);
    }
    // a text-only answer (no audio came back) still ends the turn
    if (phase === 'thinking' && answered.current && !player.speaking) {
      const id = setTimeout(() => setPhase('idle'), 1200);
      return () => clearTimeout(id);
    }
    return undefined;
  }, [phase, player.speaking, handsFree, listen]);

  useEffect(() => () => { abort.current?.abort(); recorder.cancel(); player.stop(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const micBlocked = recorder.state === 'denied' ? ta('micDenied') : recorder.state === 'unsupported' ? ta('micUnsupported') : null;

  const tapOrb = () => {
    if (phase === 'idle') listen();
    else if (phase === 'listening') send();
    else { abort.current?.abort(); player.stop(); setPhase('idle'); }
  };
  const close = () => { abort.current?.abort(); recorder.cancel(); player.stop(); router.push('/dashboard/assistant'); };

  const level = phase === 'listening' ? recorder.level : 0;
  const caption = answer.split(/(?<=[.!?।])\s+/).filter(Boolean).slice(-2).join(' ');

  return (
    <div className="fx-voice fixed inset-0 z-50 flex flex-col items-center justify-between overflow-hidden px-6 pt-6 pb-10 text-[var(--vx-ink)]" role="dialog" aria-label={t('title')}>
      <div className="fx-voice-bg" aria-hidden />

      {/* top bar */}
      <div className="relative z-10 flex w-full max-w-3xl items-center justify-between">
        <div>
          <p className="text-[0.65rem] font-medium tracking-[0.22em] text-[var(--vx-gold)] uppercase">{t('eyebrow')}</p>
          <p className="mt-1 text-sm text-[var(--vx-muted)]">{farm?.name}</p>
        </div>
        <button type="button" onClick={() => setHandsFree((h) => !h)} aria-pressed={handsFree}
          className={cn('rounded-full border px-3.5 py-1.5 text-xs transition-colors',
            handsFree ? 'border-[var(--vx-accent-line)] bg-[var(--vx-accent-soft)] text-[var(--vx-accent)]' : 'border-[var(--vx-line)] text-[var(--vx-muted)] hover:text-[var(--vx-ink)]')}>
          {handsFree ? t('handsFreeOn') : t('handsFreeOff')}
        </button>
      </div>

      {/* the orb */}
      <div className="relative z-10 flex flex-1 flex-col items-center justify-center">
        <button type="button" onClick={tapOrb} aria-label={phase === 'listening' ? t('sendNow') : t('tapToTalk')}
          className={cn('fx-orb-voice', `is-${phase}`)}
          style={{ '--lvl': level.toFixed(3) }}>
          <span className="fx-orb-layer fx-orb-a" />
          <span className="fx-orb-layer fx-orb-b" />
          <span className="fx-orb-layer fx-orb-c" />
          <span className="fx-orb-shine" />
        </button>

        <p key={phase} className="mt-12 text-lg font-medium tracking-wide text-[var(--vx-ink)]/85 animate-rise">
          {error ? '' : t(`phase.${phase}`)}
        </p>
        {error && <p className="mt-3 max-w-md text-center text-sm text-[var(--vx-danger)]">{error}</p>}
        {micBlocked && <p className="mt-3 max-w-md text-center text-sm text-[var(--vx-danger)]">{micBlocked}</p>}
      </div>

      {/* captions: what you said, what FarmXpert is saying */}
      <div className="relative z-10 w-full max-w-2xl space-y-3 text-center">
        {heard && <p className="text-sm text-[var(--vx-muted)]">“{heard}”</p>}
        {caption && (
          <p key={caption.slice(0, 24)} className="text-[1.15rem] leading-relaxed text-[var(--vx-ink)] animate-rise">{caption}</p>
        )}
      </div>

      {/* controls */}
      <div className="relative z-10 mt-8 flex items-center gap-5">
        <button type="button" onClick={tapOrb}
          aria-label={phase === 'idle' ? t('tapToTalk') : phase === 'listening' ? t('sendNow') : t('stop')}
          className={cn('grid size-16 place-items-center rounded-full transition-all',
            phase === 'listening' ? 'bg-[var(--vx-btn-on)] text-[var(--vx-btn-on-ink)] shadow-[0_0_0_8px_var(--vx-ring)]' : 'bg-[var(--vx-btn)] text-[var(--vx-ink)] hover:bg-[var(--vx-btn-hover)]')}>
          {phase === 'thinking' || phase === 'speaking' ? <Square className="size-5 fill-current" /> : <Mic className="size-6" />}
        </button>
        <button type="button" onClick={close} aria-label={t('close')}
          className="grid size-16 place-items-center rounded-full bg-[var(--vx-close)] text-[var(--vx-danger)] transition-colors hover:bg-[var(--vx-close-hover)]">
          <svg viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
            <path d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>
  );
}

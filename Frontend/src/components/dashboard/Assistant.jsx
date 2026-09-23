'use client';

// ============================================================
// FILE: src/components/dashboard/Assistant.jsx
//
// Ask FarmXpert - typed or spoken, in any Indian language.
//   typed:  /chat/ask (streamed): the answer appears as it is written
//   spoken: hold the mic, release: transcript, then the answer is
//           shown AND spoken sentence by sentence
// The farm and field come from the dashboard, so every answer is
// about this farmer's land. The app locale is only a language hint.
// ============================================================

import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { Mic, Send, Sparkles, Square, Volume2 } from 'lucide-react';

import { cn } from '@/lib/cn';
import { useFarm } from '@/context/FarmContext';
import useAudioQueue from '@/hooks/useAudioQueue';
import useVoiceRecorder from '@/hooks/useVoiceRecorder';
import { ApiError, askText, askVoice } from '@/services/api';
import Botanical from '@/components/ui/Botanical';

let nextId = 0;
const newId = () => `m${(nextId += 1)}`;

export default function Assistant() {
  const t = useTranslations('dashboard.assistant');
  const locale = useLocale();
  const search = useSearchParams();
  const { farm, field } = useFarm();
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState(() => search.get('q') || '');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const conversationId = useRef(null);
  const abort = useRef(null);
  const listEnd = useRef(null);
  const held = useRef(false);
  const recorder = useVoiceRecorder();
  const player = useAudioQueue();

  useEffect(() => { listEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [messages]);
  useEffect(() => () => abort.current?.abort(), []);

  const errorText = useCallback((code) => (t.has(`errors.${code}`) ? t(`errors.${code}`) : t('errors.generic')), [t]);
  const update = useCallback((id, patch) => {
    setMessages((all) => all.map((m) => (m.id === id ? { ...m, ...(typeof patch === 'function' ? patch(m) : patch) } : m)));
  }, []);

  const handlerFor = useCallback((farmerId, answerId) => (event, data) => {
    if (event === 'conversation') conversationId.current = data.conversation_id;
    else if (event === 'transcript') update(farmerId, { text: data.text, pending: false });
    else if (event === 'delta') update(answerId, (m) => ({ text: m.text + data.text, pending: false }));
    else if (event === 'audio') player.enqueue(data);
    else if (event === 'done') {
      update(answerId, (m) => ({ text: data.answer || m.text || data.summary || t('noAnswer'), pending: false,
        language: data.understanding?.language, agents: Object.keys(data.results || {}) }));
    } else if (event === 'error') update(answerId, { text: errorText(data.code), pending: false, failed: true });
  }, [errorText, player, t, update]);

  const run = useCallback(async (farmerMessage, send) => {
    const answerId = newId();
    setMessages((all) => [...all, farmerMessage, { id: answerId, role: 'assistant', text: '', pending: true }]);
    setBusy(true);
    setNotice(null);
    abort.current?.abort();
    abort.current = new AbortController();
    try {
      await send(handlerFor(farmerMessage.id, answerId), abort.current.signal);
    } catch (err) {
      if (err?.name === 'AbortError') return;
      update(answerId, { text: errorText(err instanceof ApiError ? err.code : 'network'), pending: false, failed: true });
      if (farmerMessage.pending) update(farmerMessage.id, { text: t('voiceNotHeard'), pending: false });
    } finally {
      setBusy(false);
    }
  }, [errorText, handlerFor, t, update]);

  const context = () => ({ farmId: farm?.id, fieldId: field?.id, conversationId: conversationId.current, language: locale });

  const sendText = (text = draft) => {
    const query = text.trim();
    if (!query || busy) return;
    setDraft('');
    player.stop();
    run({ id: newId(), role: 'farmer', text: query }, (onEvent, signal) => askText({ query, ...context() }, onEvent, signal));
  };

  const pressMic = async (e) => {
    e.preventDefault();
    if (busy) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    held.current = true;
    player.stop();
    await recorder.start();
    if (!held.current) { recorder.cancel(); setNotice(t('holdLonger')); }
  };
  const releaseMic = async () => {
    if (!held.current) return;
    held.current = false;
    const recording = await recorder.stop();
    if (!recording) { setNotice(t('holdLonger')); return; }
    run({ id: newId(), role: 'farmer', text: t('listening'), pending: true, voice: true },
      (onEvent, signal) => askVoice(recording, context(), onEvent, signal));
  };

  const recording = recorder.state === 'recording';
  const micNotice = recorder.state === 'denied' ? t('micDenied') : recorder.state === 'unsupported' ? t('micUnsupported') : null;
  const suggestions = ['water', 'fertiliser', 'weather', 'pest'].map((k) => t(`suggest.${k}`));

  return (
    <div className="mx-auto flex h-[calc(100dvh-11rem)] max-w-3xl flex-col lg:h-[calc(100dvh-5rem)]">
      <header className="mb-4 flex items-end justify-between gap-4">
        <div>
          <p className="eyebrow flex items-center gap-3 text-gold"><span className="h-px w-8 bg-gold/60" aria-hidden />{t('eyebrow')}</p>
          <h1 className="mt-2 text-3xl text-forest dark:text-ink">{t('title')} <span className="font-script text-4xl font-normal text-gold">{t('titleScript')}</span></h1>
        </div>
        {farm && <p className="hidden text-right text-xs text-faint sm:block">{t('about', { farm: farm.name })}</p>}
      </header>

      <div className="relative flex-1 overflow-hidden rounded-[1.75rem] border border-line bg-surface shadow-card">
        <Botanical name="corner" className="-top-10 -right-12 w-56 -scale-x-100 opacity-[0.07]" />
        <ol className="relative h-full space-y-4 overflow-y-auto px-4 py-6 sm:px-6" aria-live="polite">
          {messages.length === 0 && (
            <li className="flex h-full flex-col items-center justify-center text-center">
              <span className="grid size-16 place-items-center rounded-full bg-sage"><Sparkles className="size-7 text-leaf" /></span>
              <p className="mt-5 max-w-sm font-serif text-xl text-ink">{t('emptyTitle')}</p>
              <p className="mt-2 max-w-sm text-sm text-muted">{t('emptyText')}</p>
              <div className="mt-6 flex max-w-lg flex-wrap justify-center gap-2">
                {suggestions.map((s) => (
                  <button key={s} type="button" onClick={() => sendText(s)}
                    className="rounded-full border border-line bg-canvas px-4 py-2 text-sm text-ink transition-all hover:-translate-y-0.5 hover:border-leaf/50">
                    {s}
                  </button>
                ))}
              </div>
            </li>
          )}
          {messages.map((m) => (
            <li key={m.id} lang={m.language || undefined}
              className={cn('flex animate-rise', m.role === 'farmer' ? 'justify-end' : 'justify-start')}>
              <div className={cn('max-w-[85%] rounded-[1.4rem] px-4 py-3 text-[0.98rem] leading-relaxed whitespace-pre-wrap',
                m.role === 'farmer'
                  ? 'rounded-br-md bg-forest text-on-forest'
                  : cn('rounded-bl-md border bg-canvas text-ink', m.failed ? 'border-danger/30 text-muted' : 'border-line'))}>
                {m.voice && <Mic className="mr-1.5 inline size-3.5 opacity-70" aria-label={t('spoken')} />}
                {m.pending && !m.text ? (
                  <span className="inline-flex gap-1" aria-label={t('thinking')}>
                    {[0, 1, 2].map((i) => <i key={i} className="size-1.5 animate-bounce rounded-full bg-leaf" style={{ animationDelay: `${i * 0.15}s` }} />)}
                  </span>
                ) : m.text}
                {m.agents?.length > 0 && (
                  <p className="mt-2 text-[0.7rem] text-faint">{t('checkedBy', { count: m.agents.length })}</p>
                )}
              </div>
            </li>
          ))}
          <li ref={listEnd} aria-hidden />
        </ol>
      </div>

      {(notice || micNotice) && <p className="mt-2 text-center text-sm text-muted" role="status">{notice || micNotice}</p>}

      <form className="mt-3 flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); sendText(); }}>
        {player.speaking && (
          <button type="button" onClick={player.stop} aria-label={t('stopSpeaking')}
            className="grid size-12 shrink-0 place-items-center rounded-full border border-line bg-surface text-ink">
            <span className="flex"><Square className="size-3.5" /><Volume2 className="size-4" /></span>
          </button>
        )}
        <input value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={2000} disabled={recording}
          placeholder={recording ? t('listening') : t('placeholder')} aria-label={t('placeholder')}
          className="h-13 min-w-0 flex-1 rounded-full border border-line bg-surface px-5 text-[0.98rem] text-ink placeholder:text-faint focus:border-leaf focus:outline-none focus:ring-4 focus:ring-leaf/10" />
        {draft.trim() ? (
          <button type="submit" disabled={busy} aria-label={t('send')}
            className="grid size-13 shrink-0 place-items-center rounded-full bg-forest text-on-forest shadow-card transition-transform hover:-translate-y-0.5 disabled:opacity-50">
            <Send className="size-5" />
          </button>
        ) : (
          <button type="button" disabled={busy && !recording} aria-pressed={recording}
            aria-label={recording ? t('releaseToSend') : t('holdToTalk')}
            onPointerDown={pressMic} onPointerUp={releaseMic}
            onPointerCancel={() => { held.current = false; recorder.cancel(); }}
            onContextMenu={(e) => e.preventDefault()}
            style={{ boxShadow: recording ? `0 0 0 ${4 + recorder.level * 18}px color-mix(in srgb, var(--fx-gold) 35%, transparent)` : undefined }}
            className={cn('grid size-15 shrink-0 touch-none place-items-center rounded-full text-on-forest shadow-card transition-all select-none disabled:opacity-50',
              recording ? 'scale-110 bg-gold text-forest-deep' : 'bg-forest hover:-translate-y-0.5')}>
            <Mic className="size-6" />
          </button>
        )}
      </form>
      <p className="mt-2 text-center text-xs text-faint">{recording ? t('releaseToSend') : t('holdToTalk')}</p>
    </div>
  );
}

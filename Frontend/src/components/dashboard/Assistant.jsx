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
import { ArrowUp, AudioLines, Mic, Sparkles, Square, Volume2 } from '@/components/ui/icons';

import { cn } from '@/lib/cn';
import { Link } from '@/i18n/navigation';
import { useFarm } from '@/context/FarmContext';
import useAudioQueue from '@/hooks/useAudioQueue';
import { ApiError, askText } from '@/services/api';
import { useAuth } from '@/context/AuthContext';
import { AgentCredits, RevealText, ThinkingLabel } from './AnswerParts';
import AgentPicker from './AgentPicker';

let nextId = 0;
const newId = () => `m${(nextId += 1)}`;

export default function Assistant() {
  const t = useTranslations('dashboard.assistant');
  const o = useTranslations('dashboard.overview');
  const { user } = useAuth();
  const locale = useLocale();
  const search = useSearchParams();
  const { farm, field } = useFarm();
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState(() => search.get('q') || '');
  const [busy, setBusy] = useState(false);
  const [agent, setAgent] = useState('auto');      // 'auto' = the orchestrator picks the experts
  const [notice, setNotice] = useState(null);
  const conversationId = useRef(null);
  const abort = useRef(null);
  const listEnd = useRef(null);
  const player = useAudioQueue();

  const follow = useCallback(() => { listEnd.current?.scrollIntoView({ block: 'end' }); }, []);
  useEffect(() => { listEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [messages.length]);
  useEffect(() => () => abort.current?.abort(), []);

  const errorText = useCallback((code) => (t.has(`errors.${code}`) ? t(`errors.${code}`) : t('errors.generic')), [t]);
  const update = useCallback((id, patch) => {
    setMessages((all) => all.map((m) => (m.id === id ? { ...m, ...(typeof patch === 'function' ? patch(m) : patch) } : m)));
  }, []);

  const handlerFor = useCallback((farmerId, answerId) => (event, data) => {
    if (event === 'conversation') conversationId.current = data.conversation_id;
    else if (event === 'transcript') update(farmerId, { text: data.text, pending: false });
    else if (event === 'delta') update(answerId, (m) => ({ text: m.text + data.text, pending: false, streaming: true }));
    else if (event === 'audio') player.enqueue(data);
    else if (event === 'done') {
      update(answerId, (m) => ({ text: data.answer || m.text || data.summary || t('noAnswer'), pending: false, streaming: false,
        language: data.understanding?.language, agents: Object.keys(data.results || {}) }));
    } else if (event === 'error') update(answerId, { text: errorText(data.code), pending: false, streaming: false, failed: true });
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
      update(answerId, { text: errorText(err instanceof ApiError ? err.code : 'network'), pending: false, streaming: false, failed: true });
      if (farmerMessage.pending) update(farmerMessage.id, { text: t('voiceNotHeard'), pending: false });
    } finally {
      setBusy(false);
    }
  }, [errorText, handlerFor, t, update]);

  const context = () => ({ farmId: farm?.id, fieldId: field?.id, conversationId: conversationId.current, language: locale,
    ...(agent !== 'auto' && { agents: [agent] }) });

  const sendText = (text = draft) => {
    const query = text.trim();
    if (!query || busy) return;
    setDraft('');
    player.stop();
    run({ id: newId(), role: 'farmer', text: query }, (onEvent, signal) => askText({ query, ...context() }, onEvent, signal));
  };

  // short labels on the chips; tapping one asks the full question
  const suggestions = ['water', 'fertiliser', 'weather', 'pest'].map((k) => ({ key: k, label: t(`suggestShort.${k}`), query: t(`suggest.${k}`) }));

  const firstName = (user?.name || '').split(/\s+/)[0];
  const hour = new Date().getHours();
  const greeting = o(`greeting.${hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening'}`);
  const empty = messages.length === 0;

  const composer = (
    <form onSubmit={(e) => { e.preventDefault(); sendText(); }}
      className="rounded-[1.6rem] border border-line bg-surface p-2 shadow-card transition-shadow focus-within:border-leaf/40 focus-within:shadow-lift">
      <textarea value={draft} rows={1} maxLength={2000} 
        onChange={(e) => { setDraft(e.target.value); e.target.style.height = 'auto'; e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`; }}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(); } }}
        placeholder={t('placeholder')} aria-label={t('placeholder')}
        className="block max-h-[200px] min-h-[2.75rem] w-full resize-none bg-transparent px-3 pt-2.5 text-[1rem] leading-relaxed text-ink placeholder:text-faint focus:outline-none" />
      <div className="flex items-center justify-between gap-2 px-1 pt-1">
        <AgentPicker value={agent} onChange={setAgent} farmName={farm?.name} />
        <div className="flex items-center gap-1.5">
          {player.speaking && (
            <button type="button" onClick={player.stop} aria-label={t('stopSpeaking')}
              className="grid size-9 place-items-center rounded-full text-muted hover:bg-sage hover:text-ink">
              <Volume2 className="size-4" />
            </button>
          )}
          <Link href="/dashboard/voice" aria-label={t('voiceMode')} title={t('voiceMode')}
            className="grid size-9 place-items-center rounded-full bg-forest text-on-forest transition-transform hover:scale-105">
            <AudioLines className="size-[1.1rem]" />
          </Link>
          <button type="submit" disabled={busy || !draft.trim()} aria-label={t('send')}
            className="grid size-9 place-items-center rounded-full bg-forest text-on-forest transition-all hover:opacity-90 disabled:bg-line disabled:text-faint">
            {busy ? <Square className="size-3.5 fill-current" /> : <ArrowUp className="size-[1.1rem]" />}
          </button>
        </div>
      </div>
    </form>
  );

  if (empty) {
    return (
      <div className="mx-auto flex min-h-[calc(100dvh-11rem)] max-w-2xl flex-col justify-center pb-10 lg:min-h-[calc(100dvh-5rem)]">
        <div className="mb-8 text-center animate-rise">
          <Sparkles className="mx-auto mb-4 size-7 text-gold" aria-hidden />
          <h1 className="text-[2.2rem] leading-tight text-ink sm:text-[2.6rem]">
            {greeting}{firstName ? `, ${firstName}` : ''}
          </h1>
          <p className="mt-2 text-muted">{t('emptyText')}</p>
        </div>
        {composer}
        <div className="no-scrollbar mt-3 flex flex-nowrap justify-start gap-1 overflow-x-auto sm:justify-center">
          {suggestions.map((s) => (
            <button key={s.key} type="button" onClick={() => sendText(s.query)} title={s.query}
              className="shrink-0 rounded-full border border-line bg-surface px-3 py-1 text-[0.72rem] whitespace-nowrap text-muted transition-colors hover:border-leaf/40 hover:text-ink">
              {s.label}
            </button>
          ))}
        </div>
        {notice && <p className="mt-4 text-center text-sm text-muted" role="status">{notice}</p>}
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-[calc(100dvh-11rem)] max-w-3xl flex-col lg:min-h-[calc(100dvh-5rem)]">
      <ol className="flex-1 space-y-8 pb-8" aria-live="polite">
        {messages.map((m) => (m.role === 'farmer' ? (
          <li key={m.id} className="flex justify-end animate-rise">
            <div className="max-w-[80%] rounded-3xl bg-raised px-5 py-3 text-[1rem] leading-relaxed whitespace-pre-wrap text-ink ring-1 ring-line">
              {m.voice && <Mic className="mr-1.5 inline size-3.5 text-faint" aria-label={t('spoken')} />}
              {m.text}
            </div>
          </li>
        ) : (
          <li key={m.id} lang={m.language || undefined} className="flex gap-4 animate-rise">
            <span className="mt-1 grid size-7 shrink-0 place-items-center rounded-full bg-forest text-on-forest" aria-hidden>
              <Sparkles className="size-3.5" />
            </span>
            <div className="min-w-0 flex-1">
              {m.pending && !m.text ? <ThinkingLabel />
                : m.failed ? <p className="text-[1rem] text-danger">{m.text}</p>
                  : <RevealText text={m.text} streaming={!!m.streaming} onGrow={follow} />}
              {!m.streaming && <AgentCredits agents={m.agents} />}
            </div>
          </li>
        )))}
        <li ref={listEnd} aria-hidden />
      </ol>

      <div className="sticky bottom-20 z-20 -mx-2 bg-gradient-to-t from-canvas from-70% to-transparent px-2 pt-8 pb-3 lg:bottom-0">
        {composer}
        {notice && <p className="mt-2 text-center text-sm text-muted" role="status">{notice}</p>}
      </div>
    </div>
  );
}

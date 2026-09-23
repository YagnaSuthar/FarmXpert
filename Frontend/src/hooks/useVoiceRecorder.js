'use client';

// ============================================================
// FILE: src/hooks/useVoiceRecorder.js
//
// Push-to-talk recording. start() on press, stop() on release.
//
// - Opus at ~16 kbps: a 10 s question is ~20 KB, fine on 2G/3G.
// - iOS Safari cannot record Opus; it falls back to audio/mp4,
//   which the backend accepts.
// - Stops itself at MAX_SECONDS so a stuck finger cannot upload
//   minutes of field noise.
// - `level` (0-1) drives a live meter, so the farmer can see the
//   phone is hearing them.
// ============================================================

import { useCallback, useEffect, useRef, useState } from 'react';

const MAX_SECONDS = 60;
const MIN_SECONDS = 0.6;          // a tap, not a question
const PREFERRED_TYPES = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4', 'audio/webm'];

function pickMimeType() {
  if (typeof MediaRecorder === 'undefined') return null;
  return PREFERRED_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) || '';
}

/**
 * @returns {{state: 'idle'|'recording'|'denied'|'unsupported', level: number,
 *            start: () => Promise<void>, stop: () => Promise<{blob: Blob, seconds: number}|null>,
 *            cancel: () => void}}
 */
export default function useVoiceRecorder() {
  const [state, setState] = useState('idle');
  const [level, setLevel] = useState(0);
  const ref = useRef({});

  const cleanup = useCallback(() => {
    const r = ref.current;
    clearTimeout(r.limit);
    cancelAnimationFrame(r.frame);
    r.stream?.getTracks().forEach((track) => track.stop());
    r.audioContext?.close().catch(() => {});
    ref.current = {};
    setLevel(0);
  }, []);

  useEffect(() => cleanup, [cleanup]);

  const start = useCallback(async () => {
    const mimeType = pickMimeType();
    if (mimeType === null || !navigator.mediaDevices?.getUserMedia) {
      setState('unsupported');
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch {
      setState('denied');
      return;
    }

    const recorder = new MediaRecorder(stream, {
      ...(mimeType && { mimeType }),
      audioBitsPerSecond: 16000,
    });
    const chunks = [];
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);

    // Level meter from the live input.
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const audioContext = AudioCtx ? new AudioCtx() : null;
    let frame;
    if (audioContext) {
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      audioContext.createMediaStreamSource(stream).connect(analyser);
      const samples = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteTimeDomainData(samples);
        let peak = 0;
        for (const s of samples) peak = Math.max(peak, Math.abs(s - 128));
        setLevel(Math.min(1, peak / 64));
        ref.current.frame = requestAnimationFrame(tick);
      };
      frame = requestAnimationFrame(tick);
    }

    ref.current = {
      stream, recorder, chunks, audioContext, frame, startedAt: performance.now(),
      limit: setTimeout(() => ref.current.recorder?.state === 'recording' && ref.current.recorder.stop(),
        MAX_SECONDS * 1000),
    };
    recorder.start(250);
    setState('recording');
  }, []);

  const stop = useCallback(() => new Promise((resolve) => {
    const r = ref.current;
    if (!r.recorder) {
      resolve(null);
      return;
    }
    const seconds = (performance.now() - r.startedAt) / 1000;
    r.recorder.onstop = () => {
      const blob = new Blob(r.chunks, { type: r.recorder.mimeType || 'audio/webm' });
      cleanup();
      setState('idle');
      resolve(seconds < MIN_SECONDS || !blob.size ? null : { blob, seconds: Math.min(seconds, MAX_SECONDS) });
    };
    if (r.recorder.state === 'recording') r.recorder.stop();
    else r.recorder.onstop();
  }), [cleanup]);

  const cancel = useCallback(() => {
    const r = ref.current;
    if (r.recorder) r.recorder.onstop = null;
    if (r.recorder?.state === 'recording') r.recorder.stop();
    cleanup();
    setState('idle');
  }, [cleanup]);

  return { state, level, start, stop, cancel };
}

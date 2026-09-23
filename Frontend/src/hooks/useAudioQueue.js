'use client';

// ============================================================
// FILE: src/hooks/useAudioQueue.js
//
// Plays spoken answer clips strictly in sentence order, one after
// another with no gap, while later clips are still arriving.
// Clips are base64 (mp3/opus/aac) from the voice stream's `audio`
// events. stop() silences everything and forgets the queue.
// ============================================================

import { useEffect, useRef, useState } from 'react';

const MIME = { mp3: 'audio/mpeg', opus: 'audio/ogg', aac: 'audio/aac', wav: 'audio/wav' };

function toUrl(clip) {
  const bytes = Uint8Array.from(atob(clip.data), (c) => c.charCodeAt(0));
  return URL.createObjectURL(new Blob([bytes], { type: MIME[clip.format] || 'audio/mpeg' }));
}

/** The queue itself, outside React: one instance per mounted hook. */
function createQueue(onSpeaking) {
  let clips = new Map();
  let next = 0;
  let audio = null;
  let urls = [];

  function playNext() {
    if (audio) return;                        // already playing
    // Sequence numbers can skip (a sentence that failed to synthesise):
    // play the lowest one waiting, never out of order.
    const ready = [...clips.keys()].filter((seq) => seq >= next).sort((a, b) => a - b);
    if (!ready.length) {
      onSpeaking(false);
      return;
    }
    const seq = ready[0];
    const url = toUrl(clips.get(seq));
    clips.delete(seq);
    next = seq + 1;
    urls.push(url);
    const current = new Audio(url);
    audio = current;
    onSpeaking(true);
    const done = () => {
      if (audio !== current) return;
      audio = null;
      playNext();
    };
    current.onended = done;
    current.onerror = done;
    current.play().catch(done);               // autoplay refused: skip, keep order
  }

  return {
    enqueue(clip) {
      clips.set(clip.seq, clip);
      playNext();
    },
    stop() {
      if (audio) audio.pause();
      audio = null;
      urls.forEach((url) => URL.revokeObjectURL(url));
      clips = new Map();
      next = 0;
      urls = [];
      onSpeaking(false);
    },
  };
}

export default function useAudioQueue() {
  const [speaking, setSpeaking] = useState(false);
  const [queue] = useState(() => createQueue(setSpeaking));
  const stopRef = useRef(queue.stop);

  useEffect(() => () => stopRef.current(), []);

  return { speaking, enqueue: queue.enqueue, stop: queue.stop };
}

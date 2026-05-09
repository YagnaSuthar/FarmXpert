// ============================================================
// FILE: components/ui/Tagline.jsx
// Word-by-word animated tagline component.
// Smooth fade + translateY + blur with staggered timing.
// ============================================================

'use client';

import { useMemo, useEffect, useState } from 'react';

/**
 * @param {object}  props
 * @param {string}  props.text       — The tagline string to animate
 * @param {string}  [props.className] — Additional CSS class
 * @param {number}  [props.baseDelay] — Initial delay in ms before first word
 * @param {number}  [props.stagger]   — Delay increment per word in ms
 */
export default function Tagline({
  text = '',
  className = '',
  baseDelay = 400,
  stagger = 180,
}) {
  const words = useMemo(() => text.split(/\s+/).filter(Boolean), [text]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // Trigger animation after mount for smooth entrance
    const timer = setTimeout(() => setMounted(true), 100);
    return () => clearTimeout(timer);
  }, []);

  return (
    <span className={`tagline ${className}`} aria-label={text}>
      {words.map((word, i) => (
        <span
          key={`${word}-${i}`}
          className="tagline-word"
          style={{
            '--word-delay': `${baseDelay + i * stagger}ms`,
            animationPlayState: mounted ? 'running' : 'paused',
          }}
          aria-hidden="true"
        >
          {word}
          {i < words.length - 1 ? '\u00A0' : ''}
        </span>
      ))}
    </span>
  );
}

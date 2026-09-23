'use client';

// ============================================================
// FILE: src/reusablefiles/avatar/Avatar.jsx
//
// Initials avatar with an optional image. The tint is picked from the
// Frozen Lake ramp by hashing the name, so the same person keeps the
// same shade across the app without any color living in the data.
// ============================================================

import React from 'react';
import { SERIES } from '@/reusablefiles/graphs/chart.utils';

/** First letters of the first two words, uppercased. */
export function initialsOf(name = '') {
  return String(name)
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0] || '')
    .join('')
    .toUpperCase() || '—';
}

/** Stable, order-independent hash so a name always lands on one tint. */
function tintFor(name = '') {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return SERIES[h % SERIES.length];
}

export default function Avatar({
  name = '',
  src,
  size = 'md',
  ring = false,
  className = '',
  ...rest
}) {
  const label = initialsOf(name);

  return (
    <span
      className={`ui-avatar ui-avatar-${size}${ring ? ' has-ring' : ''} ${className}`.trim()}
      style={src ? undefined : { background: tintFor(name) }}
      title={name || undefined}
      {...rest}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={name} className="ui-avatar-img" />
      ) : (
        <span aria-hidden="true">{label}</span>
      )}
    </span>
  );
}

'use client';

// ============================================================
// FILE: src/reusablefiles/skeleton/Skeleton.jsx
//
// Loading placeholder primitives.
//
//   <Skeleton w="60%" h={14} />          one bar
//   <Skeleton variant="circle" w={72} /> a disc
//   <SkeletonText lines={3} />           a paragraph, last line short
//
// Sizes are passed rather than guessed so a skeleton can be built to the
// dimensions of the thing it stands in for — which is what separates a
// convincing placeholder from a row of grey boxes.
// ============================================================

import React from 'react';

const dim = (v) => (typeof v === 'number' ? `${v}px` : v);

export default function Skeleton({
  w = '100%',
  h = 12,
  radius,
  variant = 'block',
  className = '',
  style,
  ...rest
}) {
  return (
    <span
      className={`ui-skeleton ui-skeleton-${variant} ${className}`.trim()}
      style={{
        width: dim(w),
        height: variant === 'circle' ? dim(w) : dim(h),
        borderRadius: radius != null ? dim(radius) : undefined,
        ...style,
      }}
      aria-hidden="true"
      {...rest}
    />
  );
}

/** Paragraph block — the closing line is short, the way real text falls. */
export function SkeletonText({ lines = 2, h = 10, gap = 8, lastWidth = '62%', className = '' }) {
  return (
    <span className={`ui-skeleton-stack ${className}`.trim()} style={{ gap: dim(gap) }}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} h={h} w={i === lines - 1 ? lastWidth : '100%'} />
      ))}
    </span>
  );
}

/** Head of a card: title bar plus an optional subtitle bar. */
export function SkeletonCardHead({ withSubtitle = true, action = false }) {
  return (
    <div className="ui-card-head">
      <div className="ui-card-head-text" style={{ width: '100%' }}>
        <Skeleton w="46%" h={13} />
        {withSubtitle ? <Skeleton w="66%" h={9} style={{ marginTop: 7 }} /> : null}
      </div>
      {action ? <Skeleton w={74} h={28} radius={9} /> : null}
    </div>
  );
}

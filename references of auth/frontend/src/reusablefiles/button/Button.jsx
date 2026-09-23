'use client';

// ============================================================
// FILE: src/reusablefiles/button/Button.jsx
//
// The one button for the dashboard. Variants instead of one component
// per look, so a new style is a token change rather than a new file.
//
//   variant : primary | ghost | subtle | quiet | danger | icon
//   size    : sm | md | lg
//   shape   : pill | rounded
//
// Passing `href` renders a locale-aware <Link> (never `next/link` —
// that would drop the /hi, /gu prefix) while keeping identical styling.
//
// The component holds NO user-facing text: callers pass translated
// children and `ariaLabel`.
// ============================================================

import React from 'react';
import { Link } from '@/i18n/navigation';

export default function Button({
  variant = 'primary',
  size = 'md',
  shape = 'pill',
  icon = null,
  iconRight = null,
  href,
  type = 'button',
  loading = false,
  disabled = false,
  block = false,
  active = false,
  ariaLabel,
  className = '',
  children,
  ...rest
}) {
  const classes = [
    'ui-btn',
    `ui-btn-${variant}`,
    `ui-btn-${size}`,
    `ui-btn-${shape}`,
    block ? 'is-block' : '',
    active ? 'is-active' : '',
    loading ? 'is-loading' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const content = (
    <>
      {icon ? <span className="ui-btn-icon">{icon}</span> : null}
      {children ? <span className="ui-btn-label">{children}</span> : null}
      {iconRight ? <span className="ui-btn-icon">{iconRight}</span> : null}
    </>
  );

  if (href && !disabled) {
    return (
      <Link href={href} className={classes} aria-label={ariaLabel} {...rest}>
        {content}
      </Link>
    );
  }

  return (
    <button
      type={type}
      className={classes}
      disabled={disabled || loading}
      aria-label={ariaLabel}
      aria-busy={loading || undefined}
      {...rest}
    >
      {content}
    </button>
  );
}

'use client';

// ============================================================
// FILE: src/reusablefiles/pill/Pill.jsx
//
// Small status / role chip.
//
//   <Pill tone="strong">{t('roles.admin')}</Pill>
//   <Pill tone="mid" dot>{t('status.away')}</Pill>
//
// Tones stay inside the Frozen Lake family (`--dash-state-*`) —
// meaning is carried by weight, the dot and the label, not by hue.
//
// `RolePill` maps a backend role string onto the legacy
// `.meta-pill-dash.pill-<role>` classes so the roles keep the exact
// colors the dashboard already shipped.
// ============================================================

import React from 'react';

export default function Pill({
  tone = 'strong',
  size = 'md',
  dot = false,
  className = '',
  children,
  ...rest
}) {
  return (
    <span className={`ui-pill ui-pill-${tone} ui-pill-${size} ${className}`.trim()} {...rest}>
      {dot ? <i className="ui-pill-dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

/**
 * Role chip. Reuses the existing `.meta-pill-dash` role colors so the
 * user / manager / admin / super_admin badges are unchanged.
 * @param {string} role   backend role key
 * @param {string} label  translated display text
 */
export function RolePill({ role = 'user', label, className = '' }) {
  return (
    <span className={`meta-pill-dash pill-${role} ${className}`.trim()}>
      {label ?? role}
    </span>
  );
}

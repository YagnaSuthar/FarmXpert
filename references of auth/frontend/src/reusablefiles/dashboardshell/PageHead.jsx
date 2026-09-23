'use client';

// ============================================================
// FILE: src/reusablefiles/dashboardshell/PageHead.jsx
//
// Title block at the top of the main panel: eyebrow badge, heading,
// description, and a right-aligned action row.
//
// Replaces the header markup each of the four dashboards repeated.
// ============================================================

import React from 'react';

export default function PageHead({
  badge,
  title,
  subtitle,
  actions = null,
  className = '',
}) {
  return (
    <div className={`dash-page-head ${className}`.trim()}>
      <div className="dash-page-head-text">
        {badge ? <span className="dashboard-badge-dash">{badge}</span> : null}
        <h1 className="dash-page-title">{title}</h1>
        {subtitle ? <p className="dash-page-sub">{subtitle}</p> : null}
      </div>
      {actions ? <div className="dash-page-actions">{actions}</div> : null}
    </div>
  );
}

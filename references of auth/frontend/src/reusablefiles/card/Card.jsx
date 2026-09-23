'use client';

// ============================================================
// FILE: src/reusablefiles/card/Card.jsx
//
// The base dashboard surface. Everything on the board — charts, lists,
// tables, the tracker — sits on one of these, so the border, radius and
// shadow are defined in exactly one place.
//
//   tone : light  (default white card)
//        | deep   (navy gradient surface, for the highlight cards)
//        | plain  (no padding — the child owns its own box)
//
//   span : 1–12 grid columns on the dashboard grid
//
// `CardHead` is the shared title row: heading on the left, any action
// on the right.
// ============================================================

import React from 'react';

export default function Card({
  tone = 'light',
  span,
  padded = false,
  className = '',
  as: Tag = 'section',
  children,
  ...rest
}) {
  const classes = [
    'ui-card',
    `ui-card-${tone}`,
    padded ? 'is-padded' : '',
    span ? `ui-span-${span}` : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <Tag className={classes} {...rest}>
      {children}
    </Tag>
  );
}

/**
 * Title row for a card.
 * @param {React.ReactNode} title  already-translated heading
 * @param {React.ReactNode} action right-hand slot (button, pill, menu)
 */
export function CardHead({ title, subtitle, icon, action, className = '' }) {
  return (
    <div className={`ui-card-head ${className}`.trim()}>
      <div className="ui-card-head-text">
        <h3 className="ui-card-title">
          {icon ? <span className="ui-card-title-icon">{icon}</span> : null}
          {title}
        </h3>
        {subtitle ? <p className="ui-card-subtitle">{subtitle}</p> : null}
      </div>
      {action ? <div className="ui-card-head-action">{action}</div> : null}
    </div>
  );
}

/** Padded body region for cards whose head is flush to the edge. */
export function CardBody({ className = '', children, ...rest }) {
  return (
    <div className={`ui-card-body ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}

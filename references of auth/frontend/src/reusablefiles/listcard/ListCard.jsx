'use client';

// ============================================================
// FILE: src/reusablefiles/listcard/ListCard.jsx
//
// Row list on a card — the shape the old dashboard repeated by hand
// for sensors, deployments, projects and team members.
//
//   items = [{
//     id, label, sublabel, value, valueTone,
//     icon, avatar, badge, progress, meta, onClick
//   }]
//
// `variant` picks the row rhythm:
//   'split'  label left / value right  (the old .panel-item-dash)
//   'media'  icon or avatar + two-line text + trailing slot
//
// Labels arrive translated; this component adds no copy of its own.
// ============================================================

import React from 'react';
import Card, { CardHead } from '@/reusablefiles/card/Card';
import Avatar from '@/reusablefiles/avatar/Avatar';
import Pill from '@/reusablefiles/pill/Pill';
import ProgressBar from '@/reusablefiles/graphs/ProgressBar';

export default function ListCard({
  title,
  subtitle,
  icon,
  action,
  items = [],
  variant = 'split',
  span = 3,
  divided = true,
  emptyLabel,
  loading = false,
  loadingRows = 3,
  className = '',
}) {
  const rows = loading ? Array.from({ length: loadingRows }, (_, i) => ({ id: `sk-${i}` })) : items;

  return (
    <Card span={span} className={`ui-list-card ${className}`.trim()}>
      {title ? <CardHead title={title} subtitle={subtitle} icon={icon} action={action} /> : null}

      <div className={`ui-list ui-list-${variant}${divided ? ' is-divided' : ''}`}>
        {!loading && !rows.length ? (
          <p className="ui-list-empty">{emptyLabel}</p>
        ) : null}

        {rows.map((item, i) => {
          if (loading) {
            return (
              <div className="ui-list-row is-skeleton" key={item.id}>
                <span className="ui-skeleton-line" />
              </div>
            );
          }

          const Row = item.onClick ? 'button' : 'div';

          return (
            <Row
              key={item.id ?? `${item.label}-${i}`}
              type={item.onClick ? 'button' : undefined}
              className={`ui-list-row${item.onClick ? ' is-clickable' : ''}`}
              onClick={item.onClick}
            >
              {variant === 'media' && (item.icon || item.avatar) ? (
                <span className="ui-list-media">
                  {item.avatar ? (
                    <Avatar name={item.avatar.name} src={item.avatar.src} size="sm" />
                  ) : (
                    <span className="ui-list-icon">{item.icon}</span>
                  )}
                </span>
              ) : null}

              <span className="ui-list-text">
                <span className="ui-list-label">{item.label}</span>
                {item.sublabel ? <span className="ui-list-sub">{item.sublabel}</span> : null}
                {item.progress != null ? (
                  <ProgressBar
                    value={item.progress}
                    size="sm"
                    showValue={false}
                    color={item.progressColor}
                    className="ui-list-progress"
                  />
                ) : null}
              </span>

              {item.badge ? (
                <Pill tone={item.badge.tone} className="ui-list-badge">
                  {item.badge.label}
                </Pill>
              ) : null}

              {item.value != null ? (
                <span className={`ui-list-value${item.valueTone ? ` is-${item.valueTone}` : ''}`}>
                  {item.value}
                </span>
              ) : null}

              {item.trailing ?? null}
            </Row>
          );
        })}
      </div>
    </Card>
  );
}

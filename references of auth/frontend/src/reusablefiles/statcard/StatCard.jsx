'use client';

// ============================================================
// FILE: src/reusablefiles/statcard/StatCard.jsx
//
// Headline metric tile. Entirely prop driven — the dashboard passes
// data, this owns structure and styling.
//
//   <StatCard title={t('totalNodes')} value={128} icon={<Icon/>}
//             trend={{ direction:'up', label: t('vsLastMonth', {pct:12}) }}
//             tone="deep" spark={[4,9,6,12]} />
//
// `tone="deep"` is the navy highlight surface — it paints the shared
// generative texture behind the content.
// ============================================================

import React from 'react';
import Card from '@/reusablefiles/card/Card';
import GenerativeTexture from '@/reusablefiles/texture/GenerativeTexture';
import Sparkline from '@/reusablefiles/graphs/Sparkline';

const TrendIcon = ({ direction }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {direction === 'down'
      ? <path d="M12 5v14M5 12l7 7 7-7" />
      : <path d="M12 19V5M5 12l7-7 7 7" />}
  </svg>
);

export default function StatCard({
  title,
  value,
  icon = null,
  trend = null,
  tone = 'light',
  span = 3,
  spark = null,
  loading = false,
  textureSeed = 'stat',
  onClick,
  className = '',
}) {
  const isDeep = tone === 'deep';

  return (
    <Card
      tone={tone}
      span={span}
      className={`ui-stat${onClick ? ' is-clickable' : ''} ${className}`.trim()}
      onClick={onClick}
    >
      {isDeep ? <GenerativeTexture variant={textureSeed} /> : null}

      <div className="ui-stat-top">
        <h3 className="ui-stat-title">{title}</h3>
        {icon ? <span className="ui-stat-icon">{icon}</span> : null}
      </div>

      <div className={`ui-stat-value${loading ? ' is-loading' : ''}`}>
        {loading ? <span className="ui-stat-skeleton" aria-hidden="true" /> : value}
      </div>

      {spark?.length ? (
        <div className="ui-stat-spark">
          <Sparkline
            data={spark}
            /* matches .ui-stat-spark's height so the viewBox stays 1:1 */
            height={26}
            area
            color={isDeep ? 'var(--dash-on-deep-accent)' : 'var(--graph-series-1)'}
          />
        </div>
      ) : null}

      {trend ? (
        <div className={`ui-stat-trend is-${trend.direction || 'flat'}`}>
          <TrendIcon direction={trend.direction} />
          <span className="ui-stat-trend-text">{trend.label}</span>
        </div>
      ) : null}
    </Card>
  );
}

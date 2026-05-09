'use client';

import React, { useMemo } from 'react';
import Button from '@/components/ui/Button';

export default function ServiceCard({
  title,
  description,
  tools = [],
  ctaLabel = 'Get started',
  onCtaClick,
  onHoverStart,
  onHoverEnd,
  className = '',
}) {
  const toolItems = useMemo(() => tools.filter(Boolean).slice(0, 8), [tools]);

  return (
    <article
      className={`service-card card card--hoverable ${className}`}
      onMouseEnter={onHoverStart}
      onMouseLeave={onHoverEnd}
      onFocus={onHoverStart}
      onBlur={onHoverEnd}
    >
      <div className="service-card__glow" aria-hidden="true" />

      <div className="service-card__body">
        <header className="service-card__header">
          <div className="service-card__kicker">Service</div>
          <h2 className="service-card__title">{title}</h2>
        </header>

        <p className="service-card__desc">{description}</p>

        <div className="service-card__tools" aria-label="Tools">
          {toolItems.map((tool) => (
            <span key={tool} className="tag">
              {tool}
            </span>
          ))}
        </div>

        <div className="service-card__actions">
          <Button size="lg" variant="primary" className="service-card__cta" onClick={onCtaClick}>
            {ctaLabel}
          </Button>
          <div className="service-card__hint">Hover this card to energize the particles.</div>
        </div>
      </div>
    </article>
  );
}

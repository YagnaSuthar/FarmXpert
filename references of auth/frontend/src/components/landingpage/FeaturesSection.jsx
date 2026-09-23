'use client';

// ============================================================
// FILE: src/components/landingpage/FeaturesSection.jsx
//
// Feature list is driven by a fixed key array — same pattern as
// AgentsSection. Icons and order live in code, copy lives in
// messages.features.items.<key>.{title,description}.
// ============================================================

import { Scale, Zap, ShieldCheck, BarChart3 } from 'lucide-react';
import { useTranslations } from 'next-intl';

const FEATURE_KEYS = [
  { key: 'multiAgent',      icon: <Scale size={20} />,      delay: '' },
  { key: 'edgeAnalytics',   icon: <Zap size={20} />,       delay: '0.1s' },
  { key: 'satelliteFusion', icon: <ShieldCheck size={20} />, delay: '0.2s' },
  { key: 'adaptiveLoop',    icon: <BarChart3 size={20} />, delay: '0.3s' },
];

export default function FeaturesSection() {
  const t = useTranslations('features');
  const tTitle = useTranslations('features.titleParts');
  const tBadge = useTranslations('features.badge');
  const tItems = useTranslations('features.items');

  return (
    <section className="features-section" id="features">
      <div className="section-container">
        <div className="feature-visual">
          <img
            className="feature-main-img"
            src="https://images.unsplash.com/photo-1625246333195-78d9c38ad449?w=700&q=80"
            alt={t('eyebrow')}
          />
          <img
            className="feature-secondary-img"
            src="https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=400&q=80"
            alt={t('eyebrow')}
          />
          <div className="feature-badge-card">
            <div className="fbc-icon"><Scale size={28} /></div>
            <span className="fbc-val">{tBadge('value')}</span>
            <span className="fbc-label">{tBadge('label')}</span>
          </div>
        </div>

        <div>
          <div className="section-eyebrow">{t('eyebrow')}</div>
          <h2 className="section-title">
            {tTitle('before')}{' '}
            <span className="text-green">{tTitle('accent')}</span>{' '}
            {tTitle('after')}
          </h2>
          <p className="section-sub">{t('intro')}</p>

          <div className="feature-list">
            {FEATURE_KEYS.map((item) => (
              <div
                key={item.key}
                className="feature-item reveal"
                style={item.delay ? { transitionDelay: item.delay } : undefined}
              >
                <div className="fi-icon">{item.icon}</div>
                <div>
                  <div className="fi-title">{tItems(`${item.key}.title`)}</div>
                  <div className="fi-desc">{tItems(`${item.key}.description`)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

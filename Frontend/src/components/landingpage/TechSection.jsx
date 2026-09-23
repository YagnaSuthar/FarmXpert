'use client';

// ============================================================
// FILE: src/components/landingpage/TechSection.jsx
//
// Tech chip labels are brand/product names (Next.js, FastAPI,
// etc.) so they intentionally stay untranslated — they're
// proper nouns. Only the surrounding copy is localized.
// ============================================================

import { useTranslations } from 'next-intl';

const TECH_CHIPS = [
  'Next.js',
  'FastAPI',
  'TensorFlow',
  'Python',
  'CNN Models',
  'LSTM Networks',
  'Transformer AI',
  'Multi-Agent Systems',
  'Real-Time Analytics',
  'Satellite APIs',
  'IoT Edge Computing',
  'PostgreSQL',
  'Redis Cache',
  'Kubernetes',
  'Docker',
  'WebSocket Streams',
];

export default function TechSection() {
  const t = useTranslations('tech');
  const tTitle = useTranslations('tech.titleParts');

  return (
    <section className="tech-section" id="tech">
      <div className="section-container">
        <div className="section-eyebrow">{t('eyebrow')}</div>
        <h2 className="section-title">
          {tTitle('before')}{' '}
          <span className="text-green">{tTitle('accent')}</span>
          <br />
          {tTitle('after')}
        </h2>
        <p className="section-sub">{t('intro')}</p>
        <div className="tech-strip reveal">
          {TECH_CHIPS.map((chip) => (
            <div key={chip} className="tech-chip">
              <span className="tc-dot"></span>
              {chip}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

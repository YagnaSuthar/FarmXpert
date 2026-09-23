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
  'React',
  'Node.js',
  'Express',
  'PostgreSQL',
  'Double-Entry Ledger',
  'ACID Transactions',
  'Role-Based Access',
  'Multi-Tenant Isolation',
  'JWT & Sessions',
  'Audit Trail',
  'Tax Engine',
  'Analytic Accounting',
  'Financial Reporting',
  'Payment Gateway',
  'Invoice PDF',
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

'use client';

// ============================================================
// FILE: src/components/landingpage/HowItWorksSection.jsx
//
// Process flow steps — fixed key array, icons in code, copy in
// messages.howItWorks.steps.<key>. Numbers stay in code because
// they're presentational (the order is the meaning), not copy
// that translators should fiddle with.
// ============================================================

import { Radio, Microscope, Handshake, CheckCircle2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

const STEP_KEYS = [
  { key: 'ingestion', num: '01', icon: <Radio size={18} />,        delay: '' },
  { key: 'analysis',  num: '02', icon: <Microscope size={18} />,   delay: '0.1s' },
  { key: 'fusion',    num: '03', icon: <Handshake size={18} />,    delay: '0.2s' },
  { key: 'action',    num: '04', icon: <CheckCircle2 size={18} />, delay: '0.3s' },
];

export default function HowItWorksSection() {
  const t = useTranslations('howItWorks');
  const tTitle = useTranslations('howItWorks.titleParts');
  const tSteps = useTranslations('howItWorks.steps');

  return (
    <section className="how-section" id="how">
      <div className="section-container">
        <div style={{ textAlign: 'center', marginBottom: 0 }}>
          <div className="section-eyebrow" style={{ justifyContent: 'center' }}>
            {t('eyebrow')}
          </div>
          <h2 className="section-title" style={{ textAlign: 'center' }}>
            {tTitle('before')}{' '}
            <span className="text-green">{tTitle('accent')}</span>{' '}
            {tTitle('after')}
          </h2>
          <p className="section-sub" style={{ margin: '0 auto', textAlign: 'center' }}>
            {t('intro')}
          </p>
        </div>

        <div className="how-grid">
          {STEP_KEYS.map((step) => (
            <div
              key={step.key}
              className="how-step reveal"
              style={step.delay ? { transitionDelay: step.delay } : undefined}
            >
              <div className="how-num-circle">
                <span className="how-num">{step.num}</span>
                <span className="how-step-icon">{step.icon}</span>
              </div>
              <div className="how-step-title">{tSteps(`${step.key}.title`)}</div>
              <div className="how-step-desc">{tSteps(`${step.key}.description`)}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

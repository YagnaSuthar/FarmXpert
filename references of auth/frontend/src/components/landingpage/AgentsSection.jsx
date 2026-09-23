'use client';

// ============================================================
// FILE: src/components/landingpage/AgentsSection.jsx
//
// Roster of the eight agents. The roster is iterated over a
// fixed list of message keys (not over a free-form array in
// JSON), so each translator works against an explicit, named
// slot rather than positional indices.
// ============================================================

import { useTranslations } from 'next-intl';

// Keep the order of agents in code, not in messages. Translators
// fill in the strings; the product team owns the order they
// appear in.
const AGENT_KEYS = [
  'soilHealth',
  'smartIrrigation',
  'pestDetection',
  'cropAdvisor',
  'yieldPrediction',
  'marketInsight',
  'growthMonitor',
  'voiceAssistant',
];

export default function AgentsSection() {
  const t = useTranslations('agents');
  const tTitle = useTranslations('agents.titleParts');
  const tRoster = useTranslations('agents.roster');

  return (
    <section className="agents-section" id="agents">
      <div className="section-container">
        <div className="agents-intro">
          <div className="section-eyebrow">{t('eyebrow')}</div>
          <h2 className="section-title">
            {tTitle('before')}{' '}
            <span className="text-green">{tTitle('accent')}</span>
            <br />
            {tTitle('after')}
          </h2>
          <p className="section-sub">{t('intro')}</p>
        </div>

        <ul className="agents-roster" aria-label={t('rosterLabel')}>
          {AGENT_KEYS.map((key) => (
            <li key={key} className="agent-entry">
              <span className="agent-entry-domain">{tRoster(`${key}.domain`)}</span>
              <span className="agent-entry-name">{tRoster(`${key}.name`)}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

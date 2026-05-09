// ============================================================
// FILE: components/sections/FeaturesSection.jsx
// Feature cards grid — AI Automation, Smart Insights,
// Real-time Analytics, and more.
// ============================================================

'use client';

import { useEffect, useRef, useState } from 'react';

// ── Feature data ─────────────────────────────────────────────
const FEATURES = [
  {
    id: 'f1',
    icon: '🤖',
    title: 'AI Automation',
    description: 'Automate repetitive farming tasks with intelligent agents that learn and adapt to your specific crop patterns and environmental conditions.',
  },
  {
    id: 'f2',
    icon: '📊',
    title: 'Smart Insights',
    description: 'Get actionable intelligence from your farm data. Our AI processes satellite imagery, weather patterns, and sensor data to deliver precise recommendations.',
  },
  {
    id: 'f3',
    icon: '⚡',
    title: 'Real-time Analytics',
    description: 'Monitor your entire farm operation in real-time with live dashboards, instant alerts, and predictive analytics for yield optimization.',
  },
  {
    id: 'f4',
    icon: '🌾',
    title: 'Crop Planning',
    description: 'AI-driven crop rotation planning, planting schedules, and harvest predictions based on historical data and market trends.',
  },
  {
    id: 'f5',
    icon: '💧',
    title: 'Resource Optimization',
    description: 'Minimize water usage, fertilizer costs, and energy consumption with precision farming techniques guided by machine learning.',
  },
  {
    id: 'f6',
    icon: '🛡️',
    title: 'Pest & Disease Detection',
    description: 'Early detection of crop diseases and pest infestations using computer vision and predictive models for timely intervention.',
  },
];

export default function FeaturesSection() {
  const sectionRef = useRef(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(section);
    return () => observer.disconnect();
  }, []);

  return (
    <section
      ref={sectionRef}
      className={`features-section section ${isVisible ? 'section-reveal--visible' : ''}`}
      id="features"
    >
      <div className="features-section__inner">

        {/* Section header */}
        <div className="section-header">
          <p className="label">Why FarmXpert</p>
          <h2 className="section-title display-md">
            Everything Your Farm Needs,<br />Powered by AI
          </h2>
          <p className="section-subtitle body-lg">
            From soil analysis to market predictions — intelligent tools
            that help you grow more with less effort.
          </p>
        </div>

        {/* Feature grid */}
        <ul className="features-section__grid" role="list">
          {FEATURES.map((feature, i) => (
            <li
              key={feature.id}
              className="feature-card"
              style={{
                '--card-delay': isVisible ? `${i * 100}ms` : '0ms',
                opacity: isVisible ? 1 : 0,
                transform: isVisible ? 'translateY(0)' : 'translateY(20px)',
                transition: `opacity 0.5s ease ${i * 100}ms, transform 0.5s ease ${i * 100}ms`,
              }}
            >
              <div className="feature-card__icon" aria-hidden="true">
                {feature.icon}
              </div>
              <h3 className="feature-card__title">{feature.title}</h3>
              <p className="feature-card__desc">{feature.description}</p>
            </li>
          ))}
        </ul>

      </div>
    </section>
  );
}

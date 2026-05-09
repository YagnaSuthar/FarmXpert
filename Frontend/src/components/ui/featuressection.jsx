// ============================================================
// FILE: components/ui/FeaturesSection.jsx
// Feature cards grid — icon, title, description per card.
// Cards revealed via ScrollReveal with staggered delays.
//
// TODO: replace FEATURES array with real content / CMS data
// TODO: swap placeholder icons with actual SVG icon components
// ============================================================

'use client';

// ── Placeholder feature data ─────────────────────────────────
const FEATURES = [
  {
    id:          'f1',
    icon:        '⬡',
    title:       'Modular Architecture',
    description: 'Every component is self-contained, composable, and tree-shakable.',
  },
  {
    id:          'f2',
    icon:        '⚡',
    title:       'Particle Engine',
    description: 'GPU-accelerated Three.js particle system with configurable shaders.',
  },
  {
    id:          'f3',
    icon:        '◎',
    title:       'Scroll Choreography',
    description: 'Intersection Observer hooks that orchestrate multi-layer reveals.',
  },
  {
    id:          'f4',
    icon:        '⬡',
    title:       'Design Tokens',
    description: 'Single source of truth for color, spacing, and motion in CSS vars.',
  },
  {
    id:          'f5',
    icon:        '⚡',
    title:       'Zero Runtime CSS',
    description: 'Pure CSS modules — no styled-components, no runtime overhead.',
  },
  {
    id:          'f6',
    icon:        '◎',
    title:       'Production Ready',
    description: 'Error boundaries, a11y roles, and semantic HTML baked in.',
  },
];

export default function FeaturesSection() {
  return (
    <section className="features section" id="features">
      <div className="container">

        {/* Section header */}
        <div className="section-header">
          <p className="label">Why this stack</p>
          <h2 className="section-title display-md">
            Everything you need,<br />nothing you don't.
          </h2>
          <p className="section-subtitle body-lg">
            {/* TODO: real copy */}
            Carefully chosen primitives that stay out of your way
            and scale as your product grows.
          </p>
        </div>

        {/* Feature grid */}
        <ul className="features__grid" role="list">
          {FEATURES.map((feature, i) => (
            <li
              key={feature.id}
              className="feature-card"
              style={{ '--card-delay': `${i * 80}ms` }}
            >
              <span className="feature-card__icon" aria-hidden="true">
                {feature.icon}
              </span>
              <h3 className="feature-card__title">{feature.title}</h3>
              <p  className="feature-card__desc">{feature.description}</p>
            </li>
          ))}
        </ul>

      </div>
    </section>
  );
}
// ============================================================
// FILE: components/ui/HeroSection.jsx
// Above-the-fold hero — headline, subheadline, CTA pair.
// Lives above the particle canvas layer (z-index: var(--z-content)).
//
// TODO: wire typewriter / split-text headline animation
// TODO: pass mouse position to ParticleCanvas for interactivity
// ============================================================

'use client';

export default function HeroSection() {
  return (
    <section className="hero section" id="hero">
      <div className="container hero__inner">

        {/* Eyebrow label */}
        <p className="hero__eyebrow label">
          {/* TODO: dynamic label or badge */}
          Now in public beta
        </p>

        {/* Headline — split for per-word animation */}
        <h1 className="hero__headline display-xl">
          {/* TODO: wrap words in <span> for stagger animation */}
          Build something
          <br />
          <em className="hero__headline-accent">unforgettable.</em>
        </h1>

        {/* Sub-headline */}
        <p className="hero__subheadline body-lg">
          {/* TODO: copy */}
          A production-grade foundation built for speed, scale,
          and visual impact — powered by a live particle system.
        </p>

        {/* CTA group */}
        <div className="hero__cta-group">
          <a href="#cta"      className="btn btn--primary btn--lg">Start building</a>
          <a href="#features" className="btn btn--ghost   btn--lg">See how it works</a>
        </div>

        {/* Scroll cue */}
        <div className="hero__scroll-cue" aria-hidden="true">
          <span className="hero__scroll-line" />
        </div>

      </div>
    </section>
  );
}
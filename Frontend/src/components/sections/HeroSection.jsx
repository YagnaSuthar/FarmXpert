// ============================================================
// FILE: components/sections/HeroSection.jsx
// FarmXpert hero — centered content with particle sphere
// behind text. Word-by-word tagline animation.
// ============================================================

'use client';

import Tagline from '@/components/ui/Tagline';

export default function HeroSection() {
  return (
    <section className="hero-section" id="hero">
      {/* Particle sphere renders behind via parent canvas layer */}
      <div className="hero-section__particle-overlay" aria-hidden="true" />

      <div className="hero-section__content">

        {/* Eyebrow badge */}
        <div className="hero-section__badge">
          <span className="hero-section__badge-dot" aria-hidden="true" />
          AI-Powered Agriculture Platform
        </div>

        {/* Word-by-word tagline */}
        <h1 className="hero-section__tagline">
          <Tagline
            text="Revolutionizing Agriculture with AI."
            baseDelay={500}
            stagger={150}
          />
        </h1>

        {/* Subtitle */}
        <p className="hero-section__subtitle">
          FarmXpert combines cutting-edge artificial intelligence with agricultural
          expertise to help farmers make smarter decisions, optimize yields, and
          build sustainable farming operations.
        </p>

        {/* CTA buttons */}
        <div className="hero-section__cta-group">
          <a href="#agents" className="btn btn--primary btn--lg">
            Explore AI Agents
          </a>
          <a href="#features" className="btn btn--ghost btn--lg">
            See Features
          </a>
        </div>

        {/* Scroll cue */}
        <div className="hero-section__scroll-cue" aria-hidden="true">
          <span className="hero-section__scroll-line" />
        </div>

      </div>
    </section>
  );
}

// ============================================================
// FILE: app/landingpage.jsx
// FarmXpert Landing Page — orchestrates all sections and a
// SINGLE Three.js particle canvas layer.
//
// Architecture:
//   - ONE fixed ParticleCanvas covering the viewport
//   - Scroll listener detects which section is visible
//   - Hero: sphere at center
//   - Agents: particles shift right + morph to agent shape
//   - Smooth interpolation via setOffset() on the particle system
// ============================================================

'use client';

import { useRef, useEffect, useCallback, useState } from 'react';

// Layout
import Navbar from '@/components/layout/Navbar';
import Footer from '@/components/layout/Footer';

// Sections
import HeroSection from '@/components/sections/HeroSection';
import AgentsSection from '@/components/sections/AgentsSection';
import FeaturesSection from '@/components/sections/FeaturesSection';
import CTASection from '@/components/sections/CTASection';

// Animation
import ParticleCanvas from '@/components/animation/particlecanvas';

export default function LandingPage() {
  const systemRef = useRef(null);
  const [currentSection, setCurrentSection] = useState('hero');

  const containerRef = useRef(null);

  // ── Scroll-driven particle positioning ──────────────────────
  useEffect(() => {
    const handleScroll = () => {
      const system = systemRef.current;
      const container = containerRef.current;
      if (!system || !container) return;

      const scrollY = window.scrollY;
      const viewH = window.innerHeight;

      const heroEl = document.getElementById('hero');
      const agentsEl = document.getElementById('agents');

      if (!heroEl || !agentsEl) return;

      // Calculate boundaries
      const heroBottom = heroEl.offsetTop + heroEl.offsetHeight;
      const agentsTop = agentsEl.offsetTop;
      const agentsBottom = agentsEl.offsetTop + agentsEl.offsetHeight;

      // 1. Determine which section is currently active
      // We consider Agents active if we've scrolled past the middle of the Hero section
      const isAgentsActive = scrollY > (heroBottom - viewH * 0.6);

      if (!isAgentsActive) {
        if (currentSection !== 'hero') {
          setCurrentSection('hero');
          // Always revert to sphere in Hero
          system.morphTo('sphere');
          system.setOffset(0, 0, 0); // Center
        }
      } else {
        if (currentSection !== 'agents') {
          setCurrentSection('agents');
          // Center the particles for the AgentOrbitSystem
          system.setOffset(0, 0, 0);
        }
      }

      // 2. Scroll Out of View (Past Agents)
      // When the user scrolls past the Agents section, we push the fixed canvas UP
      // so it appears to stay attached to the bottom of the Agents section.
      const leaveStart = agentsBottom - viewH;
      if (scrollY > leaveStart) {
        const outOffset = scrollY - leaveStart;
        container.style.transform = `translateY(-${outOffset}px)`;
      } else {
        container.style.transform = `translateY(0px)`;
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll(); // initial check

    return () => window.removeEventListener('scroll', handleScroll);
  }, [currentSection]);

  return (
    <div className="landing-shell">
      {/* Grain texture overlay */}
      <div className="noise-overlay" aria-hidden="true" />

      {/* ── SINGLE fixed Particle Canvas ────────────────────── */}
      <div
        ref={containerRef}
        className="particle-canvas-container"
        style={{ position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none' }}
      >
        <ParticleCanvas
          systemRef={systemRef}
          autoMorph={false}
          className="particle-canvas--fixed"
        />
      </div>

      {/* ── Navbar ─────────────────────────────────────────── */}
      <Navbar />

      {/* ── Main content ───────────────────────────────────── */}
      <main className="main-content">
        <HeroSection />
        <AgentsSection systemRef={systemRef} />
        <FeaturesSection />
        <CTASection />
      </main>

      {/* ── Footer ─────────────────────────────────────────── */}
      <Footer />
    </div>
  );
}
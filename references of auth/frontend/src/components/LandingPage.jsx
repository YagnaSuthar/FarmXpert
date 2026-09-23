'use client';

// ============================================================
// FILE: src/components/LandingPage.jsx
//
// Composes the landing-page section components and owns the
// global cursor + scroll-reveal effects that span the whole
// page. Moved out of /app so it can be imported by the
// locale-scoped page.jsx as a normal component module.
// ============================================================

import { useEffect } from 'react';

import Navbar from '@/components/Navbar';
import HeroSection from '@/components/landingpage/HeroSection';
import AgentsSection from '@/components/landingpage/AgentsSection';
import FeaturesSection from '@/components/landingpage/FeaturesSection';
import HowItWorksSection from '@/components/landingpage/HowItWorksSection';
import TechSection from '@/components/landingpage/TechSection';
import ChipSceneSection from '@/components/landingpage/ChipSceneSection';
import CTASection from '@/components/landingpage/CTASection';
import Footer from '@/components/Footer';

export default function LandingPage() {
  useEffect(() => {
    // ══ SCROLL REVEAL ══
    const reveals = document.querySelectorAll('.reveal');
    const revObs = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => { if (e.isIntersecting) e.target.classList.add('visible'); });
      },
      { threshold: 0.12 }
    );
    reveals.forEach((r) => revObs.observe(r));

    return () => {
      revObs.disconnect();
    };
  }, []);

  return (
    <>
      <Navbar />
      <HeroSection />
      <AgentsSection />
      <FeaturesSection />
      <HowItWorksSection />
      <TechSection />
      <ChipSceneSection />
      <CTASection />
      <Footer />
    </>
  );
}

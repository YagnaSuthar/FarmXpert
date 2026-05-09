'use client';
import { useEffect } from 'react';
import '@/styles/landingpage.css';

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
    // ══ CUSTOM CURSOR ══
    const dot = document.getElementById('cursorDot');
    const ring = document.getElementById('cursorRing');
    let mx = 0, my = 0, rx = 0, ry = 0;

    const onMouseMove = (e) => { mx = e.clientX; my = e.clientY; };
    document.addEventListener('mousemove', onMouseMove);

    function animCursor() {
      if (dot) { dot.style.left = mx + 'px'; dot.style.top = my + 'px'; }
      rx += (mx - rx) * 0.12;
      ry += (my - ry) * 0.12;
      if (ring) { ring.style.left = rx + 'px'; ring.style.top = ry + 'px'; }
      requestAnimationFrame(animCursor);
    }
    animCursor();

    document.querySelectorAll('button,a,.filter-tab,.agent-card,.snode').forEach((el) => {
      el.addEventListener('mouseenter', () => {
        if (ring) { ring.style.width = '52px'; ring.style.height = '52px'; }
        if (dot) dot.style.transform = 'translate(-50%,-50%) scale(1.5)';
      });
      el.addEventListener('mouseleave', () => {
        if (ring) { ring.style.width = '36px'; ring.style.height = '36px'; }
        if (dot) dot.style.transform = 'translate(-50%,-50%) scale(1)';
      });
    });

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
      document.removeEventListener('mousemove', onMouseMove);
      revObs.disconnect();
    };
  }, []);

  return (
    <>
      <div className="cursor-dot" id="cursorDot"></div>
      <div className="cursor-ring" id="cursorRing"></div>

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
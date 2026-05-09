// ============================================================
// FILE: components/sections/AgentsSection.jsx
// AI Agent Ecosystem visualization. 
// Fully interactive 3D particle orbit layout.
// ============================================================

'use client';

import { useEffect, useRef, useState } from 'react';
import AgentOrbitSystem from '../ecosystem/AgentOrbitSystem';

export default function AgentsSection({ systemRef }) {
  const sectionRef = useRef(null);
  const [isVisible, setIsVisible] = useState(false);

  // ── Scroll reveal ──────────────────────────────────────────
  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
        }
      },
      { threshold: 0.15 }
    );

    observer.observe(section);
    return () => observer.disconnect();
  }, []);

  return (
    <section
      ref={sectionRef}
      className="agents-section section"
      id="agents"
      style={{
        opacity: isVisible ? 1 : 0,
        transition: 'opacity 1s ease',
        minHeight: '100vh',
        position: 'relative'
      }}
    >
      <AgentOrbitSystem systemRef={systemRef} />
    </section>
  );
}

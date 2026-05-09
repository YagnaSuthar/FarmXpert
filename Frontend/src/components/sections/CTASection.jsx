// ============================================================
// FILE: components/sections/CTASection.jsx
// Bottom call-to-action — strong heading, Get Started button,
// background glow effect.
// ============================================================

'use client';

import { useEffect, useRef, useState } from 'react';

export default function CTASection() {
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
      { threshold: 0.2 }
    );

    observer.observe(section);
    return () => observer.disconnect();
  }, []);

  return (
    <section
      ref={sectionRef}
      className={`cta-section section ${isVisible ? 'section-reveal--visible' : ''}`}
      id="cta"
    >
      <div className="cta-section__inner">

        {/* Glow orb — decorative */}
        <div className="cta-section__glow" aria-hidden="true" />

        <div
          className="cta-section__content"
          style={{
            opacity: isVisible ? 1 : 0,
            transform: isVisible ? 'translateY(0)' : 'translateY(30px)',
            transition: 'opacity 0.8s ease, transform 0.8s ease',
          }}
        >
          <p className="label">Get Started Today</p>
          <h2 className="cta-section__headline">
            Ready to Transform<br />
            <span className="cta-section__headline-accent">Your Farm?</span>
          </h2>
          <p className="cta-section__subtext body-lg">
            Join thousands of farmers already using FarmXpert to increase yields,
            reduce costs, and build a more sustainable future for agriculture.
          </p>
        </div>

        <div
          className="cta-section__btn-wrap"
          style={{
            opacity: isVisible ? 1 : 0,
            transform: isVisible ? 'translateY(0)' : 'translateY(20px)',
            transition: 'opacity 0.8s ease 0.3s, transform 0.8s ease 0.3s',
          }}
        >
          <a
            href="#"
            className="btn btn--primary btn--lg glow-pulse"
            id="cta-get-started"
          >
            Get Started — It&apos;s Free
          </a>
        </div>

      </div>
    </section>
  );
}

// ============================================================
// FILE: components/layout/Navbar.jsx
// Sticky navigation bar — FarmXpert branding, nav links, CTA.
// Frosted glass effect on scroll.
// ============================================================

'use client';

import { useRef, useEffect, useState } from 'react';
import { useTheme } from '@/components/layout/ThemeProvider';

const DUMMY_LOGO = 'https://img.icons8.com/fluency/96/potted-plant.png';

const NAV_LINKS = [
  { label: 'Features', href: '#features' },
  { label: 'Agents',   href: '#agents' },
  { label: 'Contact',  href: '#cta' },
];

export default function Navbar() {
  const navRef = useRef(null);
  const [scrolled, setScrolled] = useState(false);
  const { theme, toggleTheme } = useTheme();

  useEffect(() => {
    const onScroll = () => {
      setScrolled(window.scrollY > 40);
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header
      ref={navRef}
      className={`navbar ${scrolled ? 'navbar--scrolled' : ''}`}
      id="navbar"
    >
      <div className="navbar__inner container">

        {/* Logo */}
        <a href="/" className="navbar__logo" aria-label="FarmXpert Home">
          <img
            src={DUMMY_LOGO}
            alt="FarmXpert Logo"
            className="navbar__logo-img"
            width={36}
            height={36}
          />
          <span className="navbar__logo-text">FarmXpert</span>
        </a>

        {/* Primary nav */}
        <nav className="navbar__nav" aria-label="Primary">
          <ul className="navbar__nav-list">
            {NAV_LINKS.map((link) => (
              <li key={link.label}>
                <a href={link.href} className="navbar__nav-link">
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        {/* Actions */}
        <div className="navbar__actions">
          <button 
            onClick={toggleTheme} 
            className="navbar__theme-toggle" 
            aria-label="Toggle Theme"
            style={{ 
              background: 'transparent', 
              border: 'none', 
              color: 'var(--text-main)', 
              fontSize: '1.25rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '40px',
              height: '40px',
              borderRadius: '50%',
              marginRight: '0.5rem'
            }}
          >
            {theme === 'light' ? '🌙' : '☀️'}
          </button>
          <a href="#cta" className="btn btn--primary btn--sm">
            Get Started
          </a>
        </div>

        {/* Mobile toggle */}
        <button className="navbar__mobile-toggle" aria-label="Toggle menu">
          <span />
          <span />
          <span />
        </button>

      </div>
    </header>
  );
}

// ============================================================
// FILE: components/ui/Header.jsx
// Top navigation bar — logo, nav links, CTA button.
// Sticky with backdrop blur; transparent → frosted on scroll.
//
// TODO: wire scroll-listener to toggle .header--scrolled class
// TODO: add mobile hamburger menu state + animation
// ============================================================

'use client';

import { useRef } from 'react';

export default function Header() {
  const headerRef = useRef(null);

  // TODO: useEffect → window scroll listener
  // toggles 'header--scrolled' class on headerRef.current

  return (
    <header ref={headerRef} className="header">
      <div className="header__inner container">

        {/* Logo */}
        <a href="/" className="header__logo" aria-label="Home">
          {/* TODO: replace with SVG logo or next/image */}
          <span className="header__logo-mark">◈</span>
          <span className="header__logo-text">Brand</span>
        </a>

        {/* Primary nav */}
        <nav className="header__nav" aria-label="Primary">
          <ul className="header__nav-list">
            <li><a href="#features" className="header__nav-link">Features</a></li>
            <li><a href="#about"    className="header__nav-link">About</a></li>
            <li><a href="#pricing"  className="header__nav-link">Pricing</a></li>
          </ul>
        </nav>

        {/* Actions */}
        <div className="header__actions">
          <a href="#cta" className="btn btn--primary btn--sm">
            Get started
          </a>
        </div>

      </div>
    </header>
  );
}
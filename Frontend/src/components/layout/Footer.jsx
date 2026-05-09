// ============================================================
// FILE: components/layout/Footer.jsx
// FarmXpert site footer — brand, nav columns, legal bar.
// ============================================================

'use client';

const DUMMY_LOGO = 'https://img.icons8.com/fluency/96/potted-plant.png';

const NAV_COLUMNS = [
  {
    heading: 'Product',
    links: [
      { label: 'Features',   href: '#features' },
      { label: 'AI Agents',  href: '#agents' },
      { label: 'Pricing',    href: '#pricing' },
    ],
  },
  {
    heading: 'Company',
    links: [
      { label: 'About',   href: '#about' },
      { label: 'Blog',    href: '#blog' },
      { label: 'Careers', href: '#careers' },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { label: 'Privacy Policy', href: '/privacy' },
      { label: 'Terms of Service', href: '/terms' },
    ],
  },
];

const CURRENT_YEAR = new Date().getFullYear();

export default function Footer() {
  return (
    <footer className="footer" id="footer">
      <div className="footer__inner">

        {/* Brand column */}
        <div className="footer__brand">
          <a href="/" className="footer__logo" aria-label="FarmXpert Home">
            <img
              src={DUMMY_LOGO}
              alt="FarmXpert Logo"
              className="footer__logo-img"
              width={32}
              height={32}
            />
            <span className="footer__logo-text">FarmXpert</span>
          </a>
          <p className="footer__tagline">
            Revolutionizing agriculture with intelligent AI-powered solutions for modern farming.
          </p>
        </div>

        {/* Nav columns */}
        <nav className="footer__nav" aria-label="Footer navigation">
          {NAV_COLUMNS.map((col) => (
            <div key={col.heading} className="footer__nav-col">
              <p className="footer__nav-heading">{col.heading}</p>
              <ul className="footer__nav-list">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <a href={link.href} className="footer__nav-link">
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

      </div>

      {/* Legal bar */}
      <div className="footer__legal">
        <div className="footer__legal-inner">
          <p className="footer__legal-text">
            © {CURRENT_YEAR} FarmXpert. All rights reserved.
          </p>
          <p className="footer__legal-text">
            Built with 🌱 for modern agriculture
          </p>
        </div>
      </div>

    </footer>
  );
}

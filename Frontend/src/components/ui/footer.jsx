// ============================================================
// FILE: components/ui/Footer.jsx
// Site footer — brand blurb, nav columns, legal row.
//
// TODO: populate NAV_COLUMNS with real links
// TODO: add social icon components
// ============================================================

'use client';

const NAV_COLUMNS = [
  {
    heading: 'Product',
    links: [
      { label: 'Features',  href: '#features'  },
      { label: 'Roadmap',   href: '#roadmap'   },
      { label: 'Changelog', href: '#changelog' },
    ],
  },
  {
    heading: 'Company',
    links: [
      { label: 'About',   href: '#about'   },
      { label: 'Blog',    href: '#blog'    },
      { label: 'Careers', href: '#careers' },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { label: 'Privacy', href: '/privacy' },
      { label: 'Terms',   href: '/terms'   },
    ],
  },
];

const CURRENT_YEAR = new Date().getFullYear();

export default function Footer() {
  return (
    <footer className="footer">
      <div className="container footer__inner">

        {/* Brand column */}
        <div className="footer__brand">
          <a href="/" className="footer__logo" aria-label="Home">
            <span className="footer__logo-mark">◈</span>
            <span className="footer__logo-text">Brand</span>
          </a>
          <p className="footer__tagline body-sm">
            {/* TODO: real tagline */}
            Built for builders who care about the craft.
          </p>
          {/* TODO: social icon row */}
        </div>

        {/* Nav columns */}
        <nav className="footer__nav" aria-label="Footer">
          {NAV_COLUMNS.map((col) => (
            <div key={col.heading} className="footer__nav-col">
              <p className="footer__nav-heading label">{col.heading}</p>
              <ul className="footer__nav-list">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <a href={link.href} className="footer__nav-link body-sm">
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
        <div className="container footer__legal-inner">
          <p className="caption">
            © {CURRENT_YEAR} Brand, Inc. All rights reserved.
          </p>
          {/* TODO: cookie / preferences link */}
        </div>
      </div>

    </footer>
  );
}
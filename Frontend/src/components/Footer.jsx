'use client';

import Link from 'next/link';

export default function Footer() {
  return (
    <footer>
      <Link href="/" className="footer-logo">
        Farm<span>X</span>pert
      </Link>
      <div className="footer-copy">© 2025 FarmXpert. AI-powered precision agriculture.</div>
      <div className="footer-links">
        <Link href="/privacy">Privacy</Link>
        <Link href="/terms">Terms</Link>
        <Link href="/docs">Docs</Link>
        <Link href="/contact">Contact</Link>
      </div>
    </footer>
  );
}
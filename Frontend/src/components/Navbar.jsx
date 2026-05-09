'use client';

import Link from 'next/link';
import '@/styles/navbar.css';

export default function Navbar() {
  return (
    <nav>
      <Link href="/" className="nav-logo">
        Farm<span>X</span>pert
      </Link>
      <div className="nav-links">
        <a href="#agents">AI Agents</a>
        <a href="#features">Features</a>
        <a href="#how">How It Works</a>
        <a href="#tech">Technology</a>
        <Link href="/auth/register" className="nav-cta">
          Get Started
        </Link>
      </div>
    </nav>
  );
}
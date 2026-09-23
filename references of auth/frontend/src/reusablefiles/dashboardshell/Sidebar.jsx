'use client';

// ============================================================
// FILE: src/reusablefiles/dashboardshell/Sidebar.jsx
//
// Left panel of the dashboard shell: brand, grouped navigation, and a
// free-form media slot pinned to the bottom.
//
//   groups = [{ key, label, items: [{ key, label, href, icon, badge,
//                                     active, onClick }] }]
//
// Two independent collapse behaviours, each owned by DashboardShell:
//   `open`      — the mobile drawer (slides over the content)
//   `collapsed` — the desktop icon rail (labels become hover tooltips,
//                 driven by `data-label` so no extra DOM per item)
//
// `media` takes any node — the shell does not decide what goes there.
// Navigation uses the locale-aware <Link> so /hi and /gu keep their
// prefix. Every label is passed in already translated.
// ============================================================

import React from 'react';
import { Link } from '@/i18n/navigation';

export default function Sidebar({
  brand,
  brandHref = '/',
  brandMark,
  groups = [],
  media = null,
  open = false,
  collapsed = false,
  onNavigate,
  onToggleCollapse,
  closeLabel,
  collapseLabel,
  expandLabel,
  footer = null,
}) {
  return (
    <aside className={`dash-sidebar${open ? ' is-open' : ''}`} aria-label={brand}>
      <div className="dash-brand">
        {/* The mark IS the collapse control. At rest it shows the logo; on
            hover or focus it cross-fades to a panel glyph, so the affordance
            only appears when the pointer is on it and the brand is what you
            see the rest of the time. The panel glyph states the sidebar's
            condition — its left rail is filled while open, empty while
            collapsed — rather than pointing in a direction. */}
        <button
          type="button"
          className="dash-brand-mark dash-brand-toggle"
          onClick={onToggleCollapse}
          aria-label={collapsed ? expandLabel : collapseLabel}
          aria-expanded={!collapsed}
        >
          <span className="dash-brand-glyph">{brandMark}</span>
          <span className="dash-brand-panel" aria-hidden="true">
            <svg width="17" height="17" viewBox="0 0 24 24">
              <rect
                x="3" y="4.5" width="18" height="15" rx="3.2"
                fill="none" stroke="currentColor" strokeWidth="1.8"
              />
              <path
                className="dash-toggle-rail"
                d="M9.4 4.5v15"
                fill="none" stroke="currentColor" strokeWidth="1.8"
              />
              <rect
                className="dash-toggle-fill"
                x="4.6" y="6.1" width="3.2" height="11.8" rx="1.2"
                fill="currentColor"
              />
            </svg>
          </span>
        </button>

        {/* the wordmark keeps its job as the link back to the site */}
        <Link href={brandHref} className="dash-brand-link" title={brand}>
          <span className="dash-brand-name">{brand}</span>
        </Link>

        {/* mobile: dismisses the drawer */}
        <button
          type="button"
          className="dash-sidebar-close"
          onClick={onNavigate}
          aria-label={closeLabel}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>

      {groups.map((group) => (
        <div className="dash-nav-group" key={group.key}>
          {group.label ? <p className="dash-nav-label">{group.label}</p> : null}
          <nav className="dash-nav">
            {group.items.map((item) =>
              item.href ? (
                <Link
                  key={item.key}
                  href={item.href}
                  className={`dash-nav-item${item.active ? ' is-active' : ''}`}
                  aria-current={item.active ? 'page' : undefined}
                  data-label={item.label}
                  onClick={onNavigate}
                >
                  {item.icon}
                  <span className="dash-nav-text">{item.label}</span>
                  {item.badge != null ? <span className="dash-nav-badge">{item.badge}</span> : null}
                </Link>
              ) : (
                <button
                  key={item.key}
                  type="button"
                  className={`dash-nav-item${item.active ? ' is-active' : ''}`}
                  data-label={item.label}
                  onClick={item.onClick}
                >
                  {item.icon}
                  <span className="dash-nav-text">{item.label}</span>
                  {item.badge != null ? <span className="dash-nav-badge">{item.badge}</span> : null}
                </button>
              ),
            )}
          </nav>
        </div>
      ))}

      {media ? <div className="dash-sidebar-media">{media}</div> : null}

      {footer}
    </aside>
  );
}

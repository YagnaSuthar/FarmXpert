'use client';

// ============================================================
// FILE: src/reusablefiles/dashboardshell/DashboardShell.jsx
//
// The three-panel dashboard board: sidebar / topbar / main, all
// floating on the white board with the page itself never scrolling —
// the sidebar and main panel each scroll internally, which is what
// keeps the topbar pinned where it belongs.
//
//   <DashboardShell sidebar={<Sidebar …/>} topbar={<Topbar …/>}>
//     <PageHead …/>
//     <div className="dash-grid"> …cards… </div>
//   </DashboardShell>
//
// The shell owns both panel states so pages never wire them up:
//   drawer    — below 1180px the sidebar slides over the content
//   collapsed — above it, the sidebar can shrink to an icon rail
// Both are handed down through cloneElement.
// ============================================================

import React, { useCallback, useEffect, useState, useSyncExternalStore } from 'react';

const COLLAPSE_KEY = 'furnova:sidebar-collapsed';

/**
 * The rail preference lives in localStorage, which is external state.
 * Reading it through useSyncExternalStore (rather than an effect) keeps
 * the server snapshot explicit — the server always renders expanded —
 * and picks up the change when another tab writes the key.
 */
const collapseStore = {
  listeners: new Set(),

  read() {
    try {
      return window.localStorage.getItem(COLLAPSE_KEY) === '1';
    } catch {
      return false; // storage blocked (private mode) — stay expanded
    }
  },

  write(next) {
    try {
      window.localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0');
    } catch {
      // the preference simply will not persist
    }
    collapseStore.listeners.forEach((notify) => notify());
  },

  subscribe(listener) {
    collapseStore.listeners.add(listener);
    window.addEventListener('storage', listener);
    return () => {
      collapseStore.listeners.delete(listener);
      window.removeEventListener('storage', listener);
    };
  },
};

const serverSnapshot = () => false;

export default function DashboardShell({ sidebar, topbar, children, className = '' }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const collapsed = useSyncExternalStore(
    collapseStore.subscribe,
    collapseStore.read,
    serverSnapshot,
  );

  const close = useCallback(() => setDrawerOpen(false), []);
  const toggleDrawer = useCallback(() => setDrawerOpen((v) => !v), []);
  const toggleCollapse = useCallback(() => collapseStore.write(!collapseStore.read()), []);

  // Escape closes the drawer — expected of any overlay navigation.
  useEffect(() => {
    if (!drawerOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawerOpen, close]);

  const shellClass = [
    'dash-shell',
    drawerOpen ? 'has-drawer' : '',
    collapsed ? 'is-collapsed' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={shellClass}>
      {sidebar
        ? React.cloneElement(sidebar, {
            open: drawerOpen,
            collapsed,
            onNavigate: close,
            onToggleCollapse: toggleCollapse,
          })
        : null}

      <span className="dash-scrim" onClick={close} aria-hidden="true" />

      {topbar ? React.cloneElement(topbar, { onMenuToggle: toggleDrawer }) : null}

      <main className="dash-main">{children}</main>
    </div>
  );
}

'use client';

// ============================================================
// FILE: src/reusablefiles/dashboardshell/Topbar.jsx
//
// Top panel of the dashboard shell: menu toggle (small screens),
// search, action buttons, an extras slot (language switcher lives
// here) and the signed-in user block.
//
//   actions = [{ key, icon, label, badge, onClick }]
//
// All copy is passed in translated.
// ============================================================

import React from 'react';
import InputBox from '@/reusablefiles/inputbox/InputBox';
import Avatar from '@/reusablefiles/avatar/Avatar';

const SearchIcon = () => (
  <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.2-3.2" />
  </svg>
);

export default function Topbar({
  search,
  onSearchChange,
  searchPlaceholder,
  searchHint,
  actions = [],
  extras = null,
  user = null,
  onMenuToggle,
  menuLabel,
  onUserClick,
}) {
  return (
    <header className="dash-topbar">
      <button
        type="button"
        className="dash-menu-btn"
        onClick={onMenuToggle}
        aria-label={menuLabel}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M4 7h16M4 12h16M4 17h16" />
        </svg>
      </button>

      {onSearchChange ? (
        <div className="dash-search">
          <InputBox
            value={search}
            onChange={onSearchChange}
            placeholder={searchPlaceholder}
            icon={<SearchIcon />}
            hint={searchHint}
            aria-label={searchPlaceholder}
          />
        </div>
      ) : (
        <span className="dash-search" />
      )}

      <div className="dash-top-actions">
        {actions.map((action) => (
          <button
            key={action.key}
            type="button"
            className="dash-icon-btn"
            data-key={action.key}
            onClick={action.onClick}
            aria-label={action.label}
          >
            {action.icon}
            {action.badge ? <span className="dash-icon-dot" aria-hidden="true" /> : null}
          </button>
        ))}

        {extras}

        {user ? (
          <button
            type="button"
            className="dash-user"
            onClick={onUserClick}
            aria-label={user.name}
          >
            <Avatar name={user.name} src={user.avatar} size="lg" ring />
            <span className="dash-user-who">
              <b>{user.name}</b>
              <span>{user.email}</span>
            </span>
          </button>
        ) : null}
      </div>
    </header>
  );
}

'use client';

// ============================================================
// FILE: src/reusablefiles/icons/SolidIcons.jsx
//
// Filled navigation glyphs.
//
// Why hand-authored rather than a package: lucide (already a project
// dependency) is a stroke set — filling its paths produces mush — and
// pulling in a second icon library for fourteen shapes is not worth the
// bundle. These are plain 24x24 solids on `currentColor`, so they take
// the nav row's color (including the inverted active pill) for free.
//
// Counters — the calendar's window, the gear's bore, the shield's tick —
// are knocked out with `fillRule="evenodd"` instead of a second shape in
// the background color, so the glyph stays transparent over any surface.
// ============================================================

import React from 'react';

const Glyph = ({ size = 18, children, ...rest }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="currentColor"
    aria-hidden="true"
    focusable="false"
    {...rest}
  >
    {children}
  </svg>
);

/* ------------------------------------------------------------ glyphs */

export const OverviewIcon = (p) => (
  <Glyph {...p}>
    <rect x="3" y="3" width="8" height="8" rx="2.4" />
    <rect x="13" y="3" width="8" height="8" rx="2.4" />
    <rect x="3" y="13" width="8" height="8" rx="2.4" />
    <rect x="13" y="13" width="8" height="8" rx="2.4" />
  </Glyph>
);

export const FieldsIcon = (p) => (
  <Glyph {...p}>
    <path
      fillRule="evenodd"
      d="M20.95 3.55a1.05 1.05 0 0 0-.95-.6C11.2 2.95 5.5 7.3 5.5 14.1c0 1.4.28 2.68.83 3.8l-2.07 2.07a1.05 1.05 0 1 0 1.48 1.48l2.07-2.07c1.12.55 2.4.83 3.8.83 6.8 0 11.15-5.7 11.15-14.5 0-.75-.36-1.4-.91-2.16ZM12 8.9a1.05 1.05 0 0 1 1.48 1.49l-5.3 5.3c-.36-.77-.56-1.65-.56-2.64 0-5.14 3.86-8.6 11.24-8.94-.34 7.38-3.8 11.24-8.94 11.24-.99 0-1.87-.2-2.64-.56Z"
    />
  </Glyph>
);

export const IrrigationIcon = (p) => (
  <Glyph {...p}>
    <path d="M12.87 2.66a1.05 1.05 0 0 0-1.74 0C10.05 4.3 5.4 11.5 5.4 15a6.6 6.6 0 0 0 13.2 0c0-3.5-4.65-10.7-5.73-12.34Z" />
  </Glyph>
);

export const AnalyticsIcon = (p) => (
  <Glyph {...p}>
    <rect x="3" y="12" width="4.6" height="9" rx="1.7" />
    <rect x="9.7" y="4" width="4.6" height="17" rx="1.7" />
    <rect x="16.4" y="8.5" width="4.6" height="12.5" rx="1.7" />
  </Glyph>
);

export const CalendarIcon = (p) => (
  <Glyph {...p}>
    <path
      fillRule="evenodd"
      d="M8 2a1.05 1.05 0 0 1 1.05 1.05V4h5.9v-.95a1.05 1.05 0 1 1 2.1 0V4h1.15A2.8 2.8 0 0 1 21 6.8v11.4A2.8 2.8 0 0 1 18.2 21H5.8A2.8 2.8 0 0 1 3 18.2V6.8A2.8 2.8 0 0 1 5.8 4h1.15v-.95A1.05 1.05 0 0 1 8 2ZM6.9 11.6a1.05 1.05 0 0 0-1.05 1.05v2.6c0 .58.47 1.05 1.05 1.05h3.1a1.05 1.05 0 0 0 1.05-1.05v-2.6a1.05 1.05 0 0 0-1.05-1.05H6.9Z"
    />
  </Glyph>
);

export const DeploymentsIcon = (p) => (
  <Glyph {...p}>
    <circle cx="12" cy="4.8" r="2.8" />
    <circle cx="4.9" cy="18.2" r="2.8" />
    <circle cx="19.1" cy="18.2" r="2.8" />
    <path d="M11.1 8.4 6.2 15.3l1.72 1.22 4.9-6.9zm1.8 0-.92 1.22 4.9 6.9 1.72-1.22z" />
  </Glyph>
);

export const NodesIcon = (p) => (
  <Glyph {...p}>
    <circle cx="12" cy="12" r="2.7" />
    <path d="M8.28 6.9a1.05 1.05 0 0 1-.06 1.48 5.1 5.1 0 0 0 0 7.24 1.05 1.05 0 1 1-1.44 1.53 7.2 7.2 0 0 1 0-10.3 1.05 1.05 0 0 1 1.5.05Zm7.44 0a1.05 1.05 0 0 1 1.5-.05 7.2 7.2 0 0 1 0 10.3 1.05 1.05 0 1 1-1.44-1.53 5.1 5.1 0 0 0 0-7.24 1.05 1.05 0 0 1-.06-1.48Z" />
    <path d="M5.2 3.6a1.05 1.05 0 0 1-.03 1.49 9.6 9.6 0 0 0 0 13.82 1.05 1.05 0 0 1-1.46 1.5 11.7 11.7 0 0 1 0-16.82 1.05 1.05 0 0 1 1.49.01Zm13.6 0a1.05 1.05 0 0 1 1.49-.01 11.7 11.7 0 0 1 0 16.82 1.05 1.05 0 1 1-1.46-1.5 9.6 9.6 0 0 0 0-13.82 1.05 1.05 0 0 1-.03-1.49Z" />
  </Glyph>
);

export const TeamIcon = (p) => (
  <Glyph {...p}>
    <circle cx="9.1" cy="7.4" r="3.7" />
    <path d="M9.1 12.7c-3.8 0-6.9 2.35-6.9 5.25 0 .93.75 1.68 1.68 1.68h10.44c.93 0 1.68-.75 1.68-1.68 0-2.9-3.1-5.25-6.9-5.25Z" />
    <path d="M17.3 4.3a3.1 3.1 0 1 1 0 6.2 3.1 3.1 0 0 1 0-6.2Zm-.7 8.5c3.1.32 5.4 2.32 5.4 4.8 0 .77-.63 1.4-1.4 1.4h-3.14c.13-.42.2-.86.2-1.32 0-1.9-.83-3.6-2.16-4.83.35-.03.72-.05 1.1-.05Z" />
  </Glyph>
);

export const RolesIcon = (p) => (
  <Glyph {...p}>
    <path
      fillRule="evenodd"
      d="M11.6 2.09a1.05 1.05 0 0 1 .8 0l7.2 3.02c.39.16.65.55.65.97v5.09c0 4.6-3 8.72-7.65 10.66a1.05 1.05 0 0 1-.8 0C7.15 19.89 4.15 15.77 4.15 11.17V6.08c0-.42.26-.81.65-.97l7.2-3.02Zm4.4 6.63a1.05 1.05 0 0 0-1.5 0l-3.62 3.66-1.28-1.3a1.05 1.05 0 1 0-1.5 1.48l2.03 2.06c.41.42 1.09.42 1.5 0l4.37-4.42a1.05 1.05 0 0 0 0-1.48Z"
    />
  </Glyph>
);

export const SystemIcon = (p) => (
  <Glyph {...p}>
    <path
      fillRule="evenodd"
      d="M8.6 1.9a1.05 1.05 0 0 1 1.05 1.05V4h1.8V2.95a1.05 1.05 0 1 1 2.1 0V4h1.8V2.95a1.05 1.05 0 1 1 2.1 0V4h.05A2.8 2.8 0 0 1 20.3 6.8v.05h1.05a1.05 1.05 0 1 1 0 2.1H20.3v1.8h1.05a1.05 1.05 0 1 1 0 2.1H20.3v1.8h1.05a1.05 1.05 0 1 1 0 2.1H20.3v.05a2.8 2.8 0 0 1-2.8 2.8h-.05v1.05a1.05 1.05 0 1 1-2.1 0V19.6h-1.8v1.05a1.05 1.05 0 1 1-2.1 0V19.6h-1.8v1.05a1.05 1.05 0 1 1-2.1 0V19.6H6.5a2.8 2.8 0 0 1-2.8-2.8v-.05H2.65a1.05 1.05 0 1 1 0-2.1H3.7v-1.8H2.65a1.05 1.05 0 1 1 0-2.1H3.7v-1.8H2.65a1.05 1.05 0 0 1 0-2.1H3.7V6.8A2.8 2.8 0 0 1 6.5 4h.05V2.95A1.05 1.05 0 0 1 8.6 1.9ZM9.5 9.15a1.05 1.05 0 0 0-1.05 1.05v3.6c0 .58.47 1.05 1.05 1.05h5a1.05 1.05 0 0 0 1.05-1.05v-3.6a1.05 1.05 0 0 0-1.05-1.05h-5Z"
    />
  </Glyph>
);

export const SettingsIcon = (p) => (
  <Glyph {...p}>
    <path
      fillRule="evenodd"
      d="M13.6 2.2c.52 0 .96.38 1.04.9l.25 1.66c.47.19.92.45 1.32.75l1.57-.62a1.05 1.05 0 0 1 1.29.45l1.6 2.77c.26.45.16 1.03-.24 1.35l-1.31 1.08c.04.28.06.57.06.86s-.02.58-.06.86l1.31 1.08c.4.32.5.9.24 1.35l-1.6 2.77a1.05 1.05 0 0 1-1.29.45l-1.57-.62c-.4.3-.85.56-1.32.75l-.25 1.66c-.08.52-.52.9-1.04.9h-3.2c-.52 0-.96-.38-1.04-.9l-.25-1.66a7.6 7.6 0 0 1-1.32-.75l-1.57.62a1.05 1.05 0 0 1-1.29-.45l-1.6-2.77a1.05 1.05 0 0 1 .24-1.35l1.31-1.08a7 7 0 0 1 0-1.72L3.86 9.8a1.05 1.05 0 0 1-.24-1.35l1.6-2.77a1.05 1.05 0 0 1 1.29-.45l1.57.62c.4-.3.85-.56 1.32-.75l.25-1.66c.08-.52.52-.9 1.04-.9h3.2ZM12 8.6a3.4 3.4 0 1 0 0 6.8 3.4 3.4 0 0 0 0-6.8Z"
    />
  </Glyph>
);

export const HelpIcon = (p) => (
  <Glyph {...p}>
    <path
      fillRule="evenodd"
      d="M12 2.2a9.8 9.8 0 1 0 0 19.6 9.8 9.8 0 0 0 0-19.6Zm0 13.35a1.3 1.3 0 1 1 0 2.6 1.3 1.3 0 0 1 0-2.6Zm0-9.9a3.6 3.6 0 0 1 2.16 6.48c-.6.45-.79.72-.79 1.02v.3a1.28 1.28 0 0 1-2.56 0v-.3c0-1.44.82-2.34 1.6-2.93a1.04 1.04 0 1 0-1.66-.83 1.28 1.28 0 1 1-2.56 0A3.6 3.6 0 0 1 12 5.65Z"
    />
  </Glyph>
);

export const LogoutIcon = (p) => (
  <Glyph {...p}>
    <path d="M13.4 2.6H7.9a3.3 3.3 0 0 0-3.3 3.3v12.2a3.3 3.3 0 0 0 3.3 3.3h5.5a1.05 1.05 0 1 0 0-2.1H7.9a1.2 1.2 0 0 1-1.2-1.2V5.9c0-.66.54-1.2 1.2-1.2h5.5a1.05 1.05 0 1 0 0-2.1Z" />
    <path d="M16.98 7.36a1.05 1.05 0 0 0-1.49 1.48l2.16 2.11H11.3a1.05 1.05 0 1 0 0 2.1h6.35l-2.16 2.11a1.05 1.05 0 1 0 1.49 1.48l3.98-3.9a1.05 1.05 0 0 0 0-1.5l-3.98-3.88Z" />
  </Glyph>
);

/* ------------------------------------------------------------ lookup */

/** Keyed by the nav key in dashboard.config.js. */
export const SOLID_ICONS = {
  overview: OverviewIcon,
  fields: FieldsIcon,
  irrigation: IrrigationIcon,
  analytics: AnalyticsIcon,
  calendar: CalendarIcon,
  deployments: DeploymentsIcon,
  nodes: NodesIcon,
  team: TeamIcon,
  directory: TeamIcon,
  roles: RolesIcon,
  system: SystemIcon,
  settings: SettingsIcon,
  help: HelpIcon,
  logout: LogoutIcon,
};

/** Render by key; falls back to the grid so a new key never renders blank. */
export default function SolidIcon({ name, size = 18, ...rest }) {
  const Icon = SOLID_ICONS[name] || OverviewIcon;
  return <Icon size={size} {...rest} />;
}

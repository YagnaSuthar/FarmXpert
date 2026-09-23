// ============================================================
// FILE: src/config/dashboard.config.js
//
// Structure of the dashboard: which nav entries each role sees, which
// icon sits on which tile, and the shared icon size.
//
// Only KEYS live here — never display text. Pages resolve every key
// through `useTranslations('dashboard')`, so adding a locale needs no
// change to this file.
// ============================================================

import {
  Activity, Bell, Gauge, LeafyGreen, LogOut, Mail, Radio,
  Shield, ShieldCheck, Thermometer, TrendingUp, Users, Droplets,
  FileText, Receipt, Wallet, Landmark, AlertTriangle, CreditCard, BookOpen,
} from 'lucide-react';

// Navigation uses the filled set; stat tiles and the topbar stay on the
// stroke set, so the sidebar reads as chrome and content icons as content.
import { SOLID_ICONS } from '@/reusablefiles/icons';

/** One icon size across the whole dashboard. */
export const ICON = 19;
export const ICON_SM = 15;

/**
 * Navigation per role.
 *   groupKey / itemKey resolve to `dashboard.nav.<key>` in messages.
 *   `href` is a locale-agnostic path — <Link> adds the prefix.
 */
export const DASHBOARD_NAV = {
  // Contact (customer / vendor). Deliberately the narrowest surface in the
  // app: their own documents only, never anything organization-wide.
  // A customer sees invoices raised to them and can pay an unpaid one by
  // card; a vendor sees the bills the organization has raised against them.
  user: [
    {
      key: 'menu',
      items: [
        { key: 'overview', icon: SOLID_ICONS.overview, href: '/dashboard/user' },
        { key: 'invoices', icon: SOLID_ICONS.fields },
        { key: 'bills', icon: SOLID_ICONS.deployments },
        { key: 'payments', icon: SOLID_ICONS.irrigation },
        { key: 'statements', icon: SOLID_ICONS.analytics },
      ],
    },
  ],
  // Invoicing User (Accountant). Adds contacts and records transactions,
  // and may update product prices — but adding or deleting products and
  // other master data stays with the business owner.
  manager: [
    {
      key: 'menu',
      items: [
        { key: 'overview', icon: SOLID_ICONS.overview, href: '/dashboard/manager' },
        { key: 'contacts', icon: SOLID_ICONS.team },
        { key: 'products', icon: SOLID_ICONS.fields },
        { key: 'sales', icon: SOLID_ICONS.deployments },
        { key: 'purchases', icon: SOLID_ICONS.nodes },
        { key: 'payments', icon: SOLID_ICONS.irrigation },
        { key: 'reports', icon: SOLID_ICONS.analytics },
      ],
    },
  ],
  // Business Owner. The only role that self-registers, the only one that
  // creates user accounts, and the only one that may add, modify or
  // archive master data.
  admin: [
    {
      key: 'menu',
      items: [
        { key: 'overview', icon: SOLID_ICONS.overview, href: '/dashboard/admin' },
        { key: 'masters', icon: SOLID_ICONS.fields },
        { key: 'contacts', icon: SOLID_ICONS.team },
        { key: 'transactions', icon: SOLID_ICONS.deployments },
        { key: 'payments', icon: SOLID_ICONS.irrigation },
        { key: 'budgets', icon: SOLID_ICONS.calendar },
        { key: 'reports', icon: SOLID_ICONS.analytics },
        { key: 'users', icon: SOLID_ICONS.directory },
        { key: 'system', icon: SOLID_ICONS.system },
      ],
    },
  ],
  super_admin: [
    {
      key: 'menu',
      items: [
        { key: 'overview', icon: SOLID_ICONS.overview, href: '/dashboard/super-admin' },
        { key: 'directory', icon: SOLID_ICONS.directory },
        { key: 'roles', icon: SOLID_ICONS.roles },
        { key: 'analytics', icon: SOLID_ICONS.analytics },
        { key: 'system', icon: SOLID_ICONS.system },
      ],
    },
  ],
};

/** Second nav group — identical for every role. */
export const GENERAL_NAV = {
  key: 'general',
  items: [
    { key: 'settings', icon: SOLID_ICONS.settings },
    { key: 'help', icon: SOLID_ICONS.help },
  ],
};

/** Icons used by the stat tiles, keyed by metric. */
export const STAT_ICONS = {
  // ── accounting metrics ──────────────────────────────────
  invoices: FileText,
  bills: Receipt,
  receivable: Landmark,
  payable: Receipt,
  cash: Wallet,
  profit: TrendingUp,
  overdue: AlertTriangle,
  payments: CreditCard,
  ledger: BookOpen,
  // ── generic / directory metrics ─────────────────────────
  nodes: Radio,
  moisture: Droplets,
  temperature: Thermometer,
  health: LeafyGreen,
  yield: TrendingUp,
  uptime: Activity,
  latency: Gauge,
  users: Users,
  verified: ShieldCheck,
  pending: Shield,
  roles: Users,
  mail: Mail,
  alerts: Bell,
  logout: LogOut,
};

/** Chart id -> which `--graph-series-*` slot it leads with. */
export const SERIES_SLOT = {
  primary: 0,
  secondary: 2,
  tertiary: 4,
  muted: 6,
};

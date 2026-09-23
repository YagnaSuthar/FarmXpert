'use client';

// ============================================================
// FILE: src/components/dashboard/DashboardFrame.jsx
//
// App-level composition of the reusable shell. Every dashboard route
// renders through this, so the guard, sidebar, topbar, navigation and
// logout are wired exactly once instead of four times.
//
//   <DashboardFrame role="user" activeKey="overview">
//     <PageHead …/>
//     <div className="dash-grid"> …cards… </div>
//   </DashboardFrame>
//
// The shell itself lives in src/reusablefiles/dashboardshell/ — this
// file only supplies the app's data (auth user, nav config, i18n).
// ============================================================

import React, { useMemo, useState } from 'react';
import Image from 'next/image';
import { useTranslations } from 'next-intl';
import { Bell, LeafyGreen, Mail } from 'lucide-react';
import { SOLID_ICONS } from '@/reusablefiles/icons';

import sidebarArt from '@/assets/STaCOFXUuo.gif';

import ProtectedRoute from '@/components/auth/ProtectedRoute';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { useAuth } from '@/context/AuthContext';
import { DASHBOARD_NAV, GENERAL_NAV, ICON } from '@/config/dashboard.config';
import {
  DashboardShell,
  Sidebar,
  Topbar,
} from '@/reusablefiles/dashboardshell';

export default function DashboardFrame({
  role,
  activeKey = 'overview',
  allowedRoles,
  search,
  onSearchChange,
  children,
}) {
  const t = useTranslations('dashboard');
  const { user, logout } = useAuth();
  const [internalSearch, setInternalSearch] = useState('');

  const searchValue = onSearchChange ? search : internalSearch;
  const handleSearch = onSearchChange || setInternalSearch;

  const groups = useMemo(() => {
    const roleGroups = DASHBOARD_NAV[role] || DASHBOARD_NAV.user;

    const mapItems = (items) =>
      items.map((item) => {
        const Icon = item.icon;
        return {
          key: item.key,
          label: t(`nav.${item.key}`),
          href: item.href,
          // solid glyphs are fill-based — no stroke weight to set
          icon: <Icon size={ICON} />,
          active: item.key === activeKey,
          badge: item.badge,
          // Entries without a route are not linkable yet; keep them
          // inert rather than sending the user to a 404.
          onClick: item.href ? undefined : () => {},
        };
      });

    return [
      ...roleGroups.map((g) => ({
        key: g.key,
        label: t(`nav.${g.key}`),
        items: mapItems(g.items),
      })),
      {
        key: GENERAL_NAV.key,
        label: t(`nav.${GENERAL_NAV.key}`),
        items: [
          ...mapItems(GENERAL_NAV.items),
          {
            key: 'logout',
            label: t('common.logout'),
            icon: <SOLID_ICONS.logout size={ICON} />,
            onClick: logout,
          },
        ],
      },
    ];
  }, [role, activeKey, t, logout]);

  const sidebar = (
    <Sidebar
      brand="Furnova"
      brandHref="/"
      brandMark={<LeafyGreen size={19} strokeWidth={1.9} aria-hidden="true" />}
      groups={groups}
      closeLabel={t('common.closeMenu')}
      collapseLabel={t('common.collapseMenu')}
      expandLabel={t('common.expandMenu')}
      media={
        /* decorative — `unoptimized` keeps the GIF animated, which the
           default image pipeline would flatten to a still frame */
        <Image
          src={sidebarArt}
          alt=""
          aria-hidden="true"
          unoptimized
          loading="eager"
          className="dash-sidebar-art"
        />
      }
    />
  );

  const topbar = (
    <Topbar
      search={searchValue}
      onSearchChange={handleSearch}
      searchPlaceholder={t('common.search')}
      menuLabel={t('common.openMenu')}
      actions={[
        {
          key: 'messages',
          label: t('common.messages'),
          icon: <Mail size={17} strokeWidth={1.8} aria-hidden="true" />,
        },
        {
          key: 'notifications',
          label: t('common.notifications'),
          icon: <Bell size={17} strokeWidth={1.8} aria-hidden="true" />,
          badge: true,
        },
      ]}
      extras={<LanguageSwitcher />}
      user={user ? { name: user.name || '', email: user.email || '' } : null}
    />
  );

  return (
    <ProtectedRoute allowedRoles={allowedRoles || [role]}>
      <DashboardShell sidebar={sidebar} topbar={topbar}>
        {children}
      </DashboardShell>
    </ProtectedRoute>
  );
}

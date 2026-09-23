'use client';

// TEMPORARY visual-check route — deleted after the screenshot pass.

import React from 'react';
import { useTranslations } from 'next-intl';
import { LeafyGreen, Bell, Mail } from 'lucide-react';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { DashboardShell, Sidebar, Topbar, PageHead } from '@/reusablefiles/dashboardshell';
import { SOLID_ICONS } from '@/reusablefiles/icons';
import { ICON } from '@/config/dashboard.config';

export default function Preview() {
  const t = useTranslations('dashboard');
  const icon = (k) => { const I = SOLID_ICONS[k]; return <I size={ICON} />; };
  const groups = [{
    key: 'menu',
    label: t('nav.menu'),
    items: [
      { key: 'overview', label: t('nav.overview'), icon: icon('overview'), active: true, onClick: () => {} },
      { key: 'fields', label: t('nav.invoices'), icon: icon('fields'), badge: 8, onClick: () => {} },
      { key: 'analytics', label: t('nav.analytics'), icon: icon('analytics'), onClick: () => {} },
    ],
  }];
  return (
    <DashboardShell
      sidebar={
        <Sidebar
          brand="Furnova" brandHref="/"
          brandMark={<LeafyGreen size={19} strokeWidth={1.9} />}
          groups={groups}
          closeLabel={t('common.closeMenu')}
          collapseLabel={t('common.collapseMenu')}
          expandLabel={t('common.expandMenu')}
        />
      }
      topbar={
        <Topbar
          search="" onSearchChange={() => {}}
          searchPlaceholder={t('common.search')}
          menuLabel={t('common.openMenu')}
          actions={[
            { key: 'messages', label: t('common.messages'), icon: <Mail size={17} strokeWidth={1.8} /> },
            { key: 'notifications', label: t('common.notifications'), icon: <Bell size={17} strokeWidth={1.8} />, badge: true },
          ]}
          extras={<LanguageSwitcher />}
          user={{ name: 'Taha Mehmud', email: 'taha.mehmud@furnova.io' }}
        />
      }
    >
      <PageHead title="Logo toggle check" subtitle="Temporary verification route" />
    </DashboardShell>
  );
}

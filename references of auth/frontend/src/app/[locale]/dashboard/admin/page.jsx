'use client';

// ============================================================
// FILE: src/app/[locale]/dashboard/admin/page.jsx
//
// Administrator dashboard. Read-only view of the platform directory —
// role changes stay exclusive to the super-admin console.
//
// Every number and chart on this page is DERIVED FROM THE REAL user
// rows returned by /auth/admin/users (see buildDirectoryMetrics), so
// nothing here is decorative.
// ============================================================

import React, { useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { RefreshCw, Search } from 'lucide-react';

import DashboardFrame from '@/components/dashboard/DashboardFrame';
import { useAuth } from '@/context/AuthContext';
import { PageHead } from '@/reusablefiles/dashboardshell';
import Card, { CardHead, CardBody } from '@/reusablefiles/card';
import { DashboardSkeleton } from '@/reusablefiles/skeleton';
import StatCard from '@/reusablefiles/statcard';
import DataTable from '@/reusablefiles/datatable';
import InputBox from '@/reusablefiles/inputbox';
import Button from '@/reusablefiles/button';
import Pill, { RolePill } from '@/reusablefiles/pill';
import {
  BarChart, BoxPlot, DonutChart, LineChart, SemiCircleGauge, seriesColor,
} from '@/reusablefiles/graphs';

import useDashboardData from '@/hooks/useDashboardData';
import { lastMonths } from '@/services/dashboard.service';
import { STAT_ICONS, ICON_SM } from '@/config/dashboard.config';

const Icon = ({ as: C, size = ICON_SM }) =>
  C ? <C size={size} strokeWidth={2} aria-hidden="true" /> : null;

export default function AdminDashboard() {
  const t = useTranslations('dashboard');
  const { user } = useAuth();
  const [search, setSearch] = useState('');
  const { users, metrics, loading, error, refresh } = useDashboardData({ scope: 'directory' });

  const months = useMemo(
    () => lastMonths(6).map(({ month }) => t(`months.${month}`)),
    [t],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) =>
      [u.name, u.email, u.role].some((field) => field && String(field).toLowerCase().includes(q)),
    );
  }, [users, search]);

  const roleMix = useMemo(
    () =>
      (metrics?.byRole || [])
        .filter((r) => r.value > 0)
        .map((r, i) => ({ label: t(`roles.${r.role}`), value: r.value, color: seriesColor(i * 2) })),
    [metrics, t],
  );

  const ageGroups = useMemo(
    () =>
      (metrics?.ageByRole || []).map((g, i) => ({
        label: t(`roles.${g.role}`),
        values: g.values,
        color: seriesColor(i * 2),
      })),
    [metrics, t],
  );

  const verification = useMemo(
    () =>
      metrics
        ? [
            { label: t('statusLabels.verified'), value: metrics.verified, color: seriesColor(0) },
            { label: t('statusLabels.pending'), value: metrics.pending, color: seriesColor(5) },
          ]
        : [],
    [metrics, t],
  );

  const columns = useMemo(
    () => [
      {
        key: 'name',
        header: t('admin.table.name'),
        render: (u) => <span className="ui-cell-strong">{u.name}</span>,
      },
      { key: 'email', header: t('admin.table.email') },
      {
        key: 'role',
        header: t('admin.table.role'),
        render: (u) => <RolePill role={u.role} label={t(`roles.${u.role}`)} />,
      },
      {
        key: 'status',
        header: t('admin.table.status'),
        render: (u) => (
          <Pill tone={u.email_verified ? 'strong' : 'soft'} size="sm" dot>
            {u.email_verified ? t('statusLabels.verified') : t('statusLabels.pending')}
          </Pill>
        ),
      },
      {
        key: 'joined',
        header: t('admin.table.joined'),
        render: (u) => (u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'),
      },
    ],
    [t],
  );

  return (
    <DashboardFrame
      role="admin"
      activeKey="overview"
      search={search}
      onSearchChange={setSearch}
    >
      <PageHead
        title={user?.name ? `${t('admin.welcome')}, ${user.name}` : t('admin.welcome')}
        subtitle={error || t('admin.subtitle')}
        actions={
          <Button
            variant="primary"
            icon={<RefreshCw size={15} strokeWidth={2.2} />}
            onClick={refresh}
          >
            {t('common.refresh')}
          </Button>
        }
      />

      {loading && !users.length ? (
        <DashboardSkeleton layout="directory" />
      ) : (
      <div className="dash-grid">
        {/* ---------------- directory metrics ---------------- */}
        <StatCard
          tone="deep"
          span={3}
          title={t('stats.totalUsers')}
          value={metrics?.total ?? 0}
          loading={loading}
          icon={<Icon as={STAT_ICONS.users} />}
          spark={metrics?.signups}
        />
        <StatCard
          span={3}
          title={t('stats.verifiedAccounts')}
          value={metrics?.verified ?? 0}
          loading={loading}
          icon={<Icon as={STAT_ICONS.verified} />}
        />
        <StatCard
          span={3}
          title={t('stats.pendingAccounts')}
          value={metrics?.pending ?? 0}
          loading={loading}
          icon={<Icon as={STAT_ICONS.pending} />}
        />
        <StatCard
          span={3}
          title={t('stats.roleTypes')}
          value={roleMix.length}
          loading={loading}
          icon={<Icon as={STAT_ICONS.roles} />}
        />

        {/* ---------------- registrations ---------------- */}
        <Card span={6}>
          <CardHead title={t('charts.signups')} subtitle={t('charts.signupsSub')} />
          <CardBody>
            <BarChart
              data={months.map((label, i) => ({
                label,
                value: metrics?.signups?.[i] ?? 0,
              }))}
              height={206}
              ariaLabel={t('charts.signups')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

        {/* ---------------- role mix ---------------- */}
        <Card span={3}>
          <CardHead title={t('charts.roleMix')} />
          <CardBody>
            <DonutChart
              data={roleMix}
              size={158}
              centerCaption={t('stats.totalUsers')}
              ariaLabel={t('charts.roleMix')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

        {/* ---------------- verification gauge ---------------- */}
        <Card span={3}>
          <CardHead title={t('charts.verification')} />
          <CardBody>
            <SemiCircleGauge
              segments={verification}
              label={`${metrics?.verificationRate ?? 0}%`}
              caption={t('charts.verificationCaption')}
              ariaLabel={t('charts.verification')}
            />
          </CardBody>
        </Card>

        {/* ---------------- signup vs verified trend ---------------- */}
        <Card span={6}>
          <CardHead title={t('charts.analytics')} subtitle={t('charts.signupsSub')} />
          <CardBody>
            <LineChart
              categories={months}
              series={[
                { name: t('series.signups'), data: metrics?.signups || [], area: true },
                {
                  name: t('series.verified'),
                  data: metrics?.verifiedByMonth || [],
                  color: seriesColor(4),
                  dashed: true,
                },
              ]}
              height={206}
              ariaLabel={t('charts.analytics')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

        {/* ---------------- account age distribution ---------------- */}
        <Card span={6}>
          <CardHead title={t('charts.accountAge')} subtitle={t('charts.accountAgeSub')} />
          <CardBody>
            <BoxPlot
              groups={ageGroups}
              height={206}
              formatValue={(v) => Math.round(v)}
              labels={{
                min: t('box.min'), q1: t('box.q1'), median: t('box.median'),
                q3: t('box.q3'), max: t('box.max'),
              }}
              ariaLabel={t('charts.accountAge')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

        {/* ---------------- user directory ---------------- */}
        <Card span={12}>
          <CardHead
            title={t('admin.userDirectory')}
            action={
              <InputBox
                value={search}
                onChange={setSearch}
                placeholder={t('admin.searchUsers')}
                icon={<Search size={15} strokeWidth={2} aria-hidden="true" />}
                size="sm"
                className="ui-head-search"
                aria-label={t('admin.searchUsers')}
              />
            }
          />
          <CardBody>
            <DataTable
              columns={columns}
              rows={filtered}
              loading={loading}
              loadingLabel={t('common.loadingDirectory')}
              emptyLabel={t('common.noUsers')}
            />
          </CardBody>
        </Card>
      </div>
      )}
    </DashboardFrame>
  );
}

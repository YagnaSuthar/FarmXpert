'use client';

// ============================================================
// FILE: src/app/[locale]/dashboard/super-admin/page.jsx
//
// Super administrator console. Everything the admin view shows, plus
// role provisioning.
//
// SECURITY: `super_admin` is never offered as a selectable role and
// existing super-admin rows are not editable — that role is
// provisioned server-side only. `updateUserRole` in the service layer
// enforces the same allowlist a second time.
// ============================================================

import React, { useCallback, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { CircleAlert, CircleCheck, RefreshCw, Search } from 'lucide-react';

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
  AreaChart, BoxPlot, DonutChart, GroupedBarChart, SemiCircleGauge, seriesColor,
} from '@/reusablefiles/graphs';

import useDashboardData from '@/hooks/useDashboardData';
import { lastMonths, updateUserRole } from '@/services/dashboard.service';
import { STAT_ICONS, ICON_SM } from '@/config/dashboard.config';

const Icon = ({ as: C, size = ICON_SM }) =>
  C ? <C size={size} strokeWidth={2} aria-hidden="true" /> : null;

/** Roles a super admin may assign. `super_admin` is deliberately absent. */
const ASSIGNABLE_ROLES = ['user', 'manager', 'admin'];

export default function SuperAdminDashboard() {
  const t = useTranslations('dashboard');
  const { user } = useAuth();
  const [search, setSearch] = useState('');
  const [updatingId, setUpdatingId] = useState(null);
  const [statusMessage, setStatusMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  const { users, metrics, loading, error, refresh } = useDashboardData({ scope: 'directory' });

  const months = useMemo(
    () => lastMonths(6).map(({ month }) => t(`months.${month}`)),
    [t],
  );

  const handleRoleChange = useCallback(
    async (userId, nextRole) => {
      if (!ASSIGNABLE_ROLES.includes(nextRole)) return;

      setUpdatingId(userId);
      setStatusMessage('');
      setErrorMessage('');

      try {
        const res = await updateUserRole(userId, nextRole);
        if (res.success) {
          setStatusMessage(t('superAdmin.roleUpdated'));
          await refresh();
        }
      } catch (err) {
        setErrorMessage(err?.message || t('common.noData'));
      } finally {
        setUpdatingId(null);
      }
    },
    [refresh, t],
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

  const ageGroups = useMemo(
    () =>
      (metrics?.ageByRole || []).map((g, i) => ({
        label: t(`roles.${g.role}`),
        values: g.values,
        color: seriesColor(i * 2),
      })),
    [metrics, t],
  );

  const roleOptions = useMemo(
    () => ASSIGNABLE_ROLES.map((role) => ({ value: role, label: t(`superAdmin.roles.${role}`) })),
    [t],
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
        key: 'roleChange',
        header: t('superAdmin.roleChange'),
        render: (u) =>
          u.role === 'super_admin' ? (
            <span className="ui-cell-locked">{t('statusLabels.protectedRoot')}</span>
          ) : (
            <InputBox
              as="select"
              size="sm"
              value={u.role}
              options={roleOptions}
              disabled={updatingId === u.id}
              onChange={(value) => handleRoleChange(u.id, value)}
              aria-label={t('superAdmin.selectRole')}
            />
          ),
      },
    ],
    [t, roleOptions, updatingId, handleRoleChange],
  );

  return (
    <DashboardFrame
      role="super_admin"
      activeKey="overview"
      search={search}
      onSearchChange={setSearch}
    >
      <PageHead
        title={user?.name ? `${t('superAdmin.welcome')}, ${user.name}` : t('superAdmin.welcome')}
        subtitle={error || t('superAdmin.subtitle')}
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

      {statusMessage ? (
        <div className="status-banner-auth ui-dash-banner">
          <CircleCheck className="status-icon-auth" size={17} strokeWidth={2} aria-hidden="true" />
          <p className="status-desc-auth">{statusMessage}</p>
        </div>
      ) : null}

      {errorMessage ? (
        <div className="error-banner-auth ui-dash-banner">
          <CircleAlert className="error-icon-auth" size={17} strokeWidth={2} aria-hidden="true" />
          <p className="error-title-auth">{errorMessage}</p>
        </div>
      ) : null}

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

        {/* ---------------- registrations vs verification ---------------- */}
        <Card span={6}>
          <CardHead title={t('charts.signups')} subtitle={t('charts.signupsSub')} />
          <CardBody>
            <GroupedBarChart
              categories={months}
              series={[
                { name: t('series.signups'), data: metrics?.signups || [] },
                {
                  name: t('series.verified'),
                  data: metrics?.verifiedByMonth || [],
                  color: seriesColor(4),
                },
              ]}
              height={206}
              ariaLabel={t('charts.signups')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

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

        <Card span={6}>
          <CardHead title={t('charts.analytics')} subtitle={t('charts.signupsSub')} />
          <CardBody>
            <AreaChart
              categories={months}
              series={[{ name: t('series.signups'), data: metrics?.signups || [] }]}
              height={190}
              ariaLabel={t('charts.analytics')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

        <Card span={6}>
          <CardHead title={t('charts.accountAge')} subtitle={t('charts.accountAgeSub')} />
          <CardBody>
            <BoxPlot
              groups={ageGroups}
              height={190}
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

        {/* ---------------- role provisioning table ---------------- */}
        <Card span={12}>
          <CardHead
            title={t('superAdmin.userManagement')}
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

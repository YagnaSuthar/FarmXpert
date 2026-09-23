'use client';

// ============================================================
// FILE: src/app/[locale]/dashboard/manager/page.jsx
//
// Operations manager dashboard. Same reusable surfaces as the farmer
// view, fed with the regional telemetry scope plus the live
// /auth/manager/dashboard summary.
// ============================================================

import React, { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Download, RefreshCw } from 'lucide-react';

import DashboardFrame from '@/components/dashboard/DashboardFrame';
import { useAuth } from '@/context/AuthContext';
import { PageHead } from '@/reusablefiles/dashboardshell';
import Card, { CardHead, CardBody } from '@/reusablefiles/card';
import { DashboardSkeleton } from '@/reusablefiles/skeleton';
import StatCard from '@/reusablefiles/statcard';
import ListCard from '@/reusablefiles/listcard';
import Button from '@/reusablefiles/button';
import TimeTracker from '@/reusablefiles/timetracker';
import {
  AreaChart, BoxPlot, DonutChart, GroupedBarChart, HeatMap,
  RadialGauge, SemiCircleGauge, StackedBarChart, seriesColor,
} from '@/reusablefiles/graphs';

import useDashboardData from '@/hooks/useDashboardData';
import { lastMonths } from '@/services/dashboard.service';
import { STAT_ICONS, ICON_SM } from '@/config/dashboard.config';

const Icon = ({ as: C, size = ICON_SM }) =>
  C ? <C size={size} strokeWidth={2} aria-hidden="true" /> : null;

export default function ManagerDashboard() {
  const t = useTranslations('dashboard');
  const { user } = useAuth();
  const { telemetry, summary, loading, refresh } = useDashboardData({ scope: 'operations' });

  const months = useMemo(
    () => lastMonths(6).map(({ month }) => t(`months.${month}`)),
    [t],
  );
  const weekdays = useMemo(
    () => Array.from({ length: 7 }, (_, i) => t(`weekdays.${i}`)),
    [t],
  );

  const stats = telemetry?.stats;
  const trend = (value) =>
    value == null
      ? null
      : {
          direction: value >= 0 ? 'up' : 'down',
          label: t(value >= 0 ? 'trend.up' : 'trend.down', { value: Math.abs(value) }),
        };

  /* Three status series share one shape across the grouped, stacked
     and donut views, so the same data reads three ways. */
  const statusSeries = useMemo(() => {
    const m = telemetry?.monthly;
    if (!m) return [];
    return [
      { name: t('segments.synced'), data: m.synced, color: seriesColor(0) },
      { name: t('segments.syncing'), data: m.syncing, color: seriesColor(3) },
      { name: t('segments.offline'), data: m.offline, color: seriesColor(6) },
    ];
  }, [telemetry, t]);

  const progress = useMemo(
    () =>
      (telemetry?.progress || []).map((seg, i) => ({
        label: t(`segments.${seg.key}`),
        value: seg.value,
        color: seriesColor(i * 3),
      })),
    [telemetry, t],
  );

  const deployments = useMemo(
    () =>
      (telemetry?.items || []).map((item) => ({
        id: item.key,
        label: t(`fields.${item.key}`),
        value: item.value,
        progress: item.progress,
      })),
    [telemetry, t],
  );

  const nodeMix = useMemo(
    () =>
      (telemetry?.items || []).map((item, i) => ({
        label: t(`fields.${item.key}`),
        value: item.value,
        color: seriesColor(i * 2),
      })),
    [telemetry, t],
  );

  const zones = useMemo(
    () =>
      (telemetry?.zones || []).map((z, i) => ({
        label: t('zone', { zone: z.zone }),
        values: z.values,
        color: seriesColor(i),
      })),
    [telemetry, t],
  );

  const rings = useMemo(
    () =>
      (telemetry?.rings || []).map((r, i) => ({
        label: t(`rings.${r.key}`),
        value: r.value,
        max: 100,
        color: seriesColor(i * 2),
      })),
    [telemetry, t],
  );

  return (
    <DashboardFrame role="manager" activeKey="overview">
      <PageHead
        title={user?.name ? `${t('manager.welcome')}, ${user.name}` : t('manager.welcome')}
        subtitle={telemetry?.simulated ? t('common.simulated') : t('manager.subtitle')}
        actions={
          <>
            <Button
              variant="primary"
              icon={<RefreshCw size={15} strokeWidth={2.2} />}
              onClick={refresh}
            >
              {t('common.refresh')}
            </Button>
            <Button variant="ghost" icon={<Download size={15} strokeWidth={2} />}>
              {t('common.exportData')}
            </Button>
          </>
        }
      />

      {loading && !telemetry ? (
        <DashboardSkeleton layout="farm" />
      ) : (
      <div className="dash-grid">
        {/* ---------------- headline metrics ---------------- */}
        <StatCard
          tone="deep"
          span={3}
          title={t('stats.openInvoices')}
          value={stats?.nodes ?? '—'}
          loading={loading}
          icon={<Icon as={STAT_ICONS.invoices} />}
          trend={trend(stats?.nodesTrend)}
          spark={telemetry?.monthly?.synced}
        />
        <StatCard
          span={3}
          title={t('stats.receivable')}
          value={summary?.status || (stats ? `₹${stats.uptime}K` : '—')}
          loading={loading}
          icon={<Icon as={STAT_ICONS.receivable} />}
          trend={trend(stats?.healthTrend)}
        />
        <StatCard
          span={3}
          title={t('stats.payable')}
          value={summary?.systemLoad || (stats ? `₹${stats.latency}K` : '—')}
          loading={loading}
          icon={<Icon as={STAT_ICONS.payable} />}
        />
        <StatCard
          span={3}
          title={t('stats.netProfit')}
          value={stats ? `₹${stats.health}K` : '—'}
          loading={loading}
          icon={<Icon as={STAT_ICONS.profit} />}
          trend={trend(stats?.healthTrend)}
        />

        {/* ---------------- grouped bars ---------------- */}
        <Card span={6}>
          <CardHead
            title={t('charts.analytics')}
            subtitle={t('charts.analyticsSub')}
            action={<Button variant="subtle" size="sm" shape="rounded">{t('common.thisYear')}</Button>}
          />
          <CardBody>
            <GroupedBarChart
              categories={months}
              series={statusSeries}
              height={206}
              ariaLabel={t('charts.analytics')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

        {/* ---------------- semi-circular gauge ---------------- */}
        <Card span={3}>
          <CardHead title={t('charts.progress')} />
          <CardBody>
            <SemiCircleGauge
              segments={progress}
              caption={t('charts.progressCaption')}
              ariaLabel={t('charts.progress')}
            />
          </CardBody>
        </Card>

        {/* ---------------- time tracker ---------------- */}
        <TimeTracker
          span={3}
          title={t('timeTracker.title')}
          task={t('timeTracker.task')}
          initialSeconds={telemetry?.trackerSeconds ?? 0}
          pauseLabel={t('timeTracker.pause')}
          resumeLabel={t('timeTracker.resume')}
          stopLabel={t('timeTracker.stop')}
        />

        {/* ---------------- weekly readings ---------------- */}
        <Card span={5}>
          <CardHead title={t('charts.weekly')} subtitle={t('charts.weeklySub')} />
          <CardBody>
            <AreaChart
              categories={weekdays}
              series={[
                { name: t('series.moisture'), data: telemetry?.week?.moisture || [] },
                {
                  name: t('series.temperature'),
                  data: telemetry?.week?.temperature || [],
                  color: seriesColor(4),
                  dashed: true,
                },
              ]}
              height={190}
              ariaLabel={t('charts.weekly')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

        {/* ---------------- node mix donut ---------------- */}
        <Card span={3}>
          <CardHead title={t('manager.nodeHealth')} />
          <CardBody>
            <DonutChart
              data={nodeMix}
              size={158}
              centerCaption={t('stats.openInvoices')}
              ariaLabel={t('manager.nodeHealth')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

        {/* ---------------- deployment list ---------------- */}
        <ListCard
          span={4}
          title={t('manager.activeDeployments')}
          items={deployments}
          loading={loading}
          emptyLabel={t('common.noData')}
          action={<Button variant="subtle" size="sm" shape="rounded">{t('common.viewAll')}</Button>}
        />

        {/* ---------------- stacked + distribution ---------------- */}
        <Card span={6}>
          <CardHead title={t('charts.signups')} subtitle={t('charts.analyticsSub')} />
          <CardBody>
            <StackedBarChart
              categories={months}
              series={statusSeries}
              height={222}
              ariaLabel={t('charts.signups')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

        <Card span={6}>
          <CardHead title={t('charts.zoneSpread')} subtitle={t('charts.zoneSpreadSub')} />
          <CardBody>
            <BoxPlot
              groups={zones}
              height={222}
              labels={{
                min: t('box.min'), q1: t('box.q1'), median: t('box.median'),
                q3: t('box.q3'), max: t('box.max'),
              }}
              ariaLabel={t('charts.zoneSpread')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

        {/* ---------------- activity + indices ---------------- */}
        <Card span={7}>
          <CardHead title={t('charts.activity')} subtitle={t('charts.activitySub')} />
          <CardBody>
            <HeatMap
              matrix={telemetry?.activity || []}
              yLabels={weekdays}
              xLabels={Array.from({ length: 12 }, (_, i) => String(i * 2).padStart(2, '0'))}
              ariaLabel={t('charts.activity')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

        <Card span={5}>
          <CardHead title={t('charts.indices')} />
          <CardBody>
            <RadialGauge
              rings={rings}
              size={166}
              showLegend
              ariaLabel={t('charts.indices')}
            />
          </CardBody>
        </Card>
      </div>
      )}
    </DashboardFrame>
  );
}

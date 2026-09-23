'use client';

// ============================================================
// FILE: src/app/[locale]/dashboard/user/page.jsx
//
// Farmer dashboard. Layout only — every surface on this page is a
// component from src/reusablefiles/ driven by data from
// useDashboardData(). No markup is duplicated here.
// ============================================================

import React, { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Download, Plus } from 'lucide-react';

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
  AreaChart, BarChart, BoxPlot, HeatMap, RadarChart,
  RadialGauge, ScatterPlot, SemiCircleGauge, seriesColor,
} from '@/reusablefiles/graphs';

import useDashboardData from '@/hooks/useDashboardData';
import { lastMonths } from '@/services/dashboard.service';
import { STAT_ICONS, ICON_SM } from '@/config/dashboard.config';

const Icon = ({ as: C, size = ICON_SM }) =>
  C ? <C size={size} strokeWidth={2} aria-hidden="true" /> : null;

export default function UserDashboard() {
  const t = useTranslations('dashboard');
  const { user } = useAuth();
  const { telemetry, loading } = useDashboardData({ scope: 'farm' });

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

  /* ---- chart inputs, all derived from the telemetry payload ---- */

  const analytics = useMemo(
    () =>
      (telemetry?.months || []).map((value, i) => ({
        label: months[i],
        value,
        // the two oldest months have no target set — drawn hatched
        muted: i < 1,
      })),
    [telemetry, months],
  );

  const progress = useMemo(
    () =>
      (telemetry?.progress || []).map((seg, i) => ({
        label: t(`segments.${seg.key}`),
        value: seg.value,
        color: seriesColor(i * 2),
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

  const zones = useMemo(
    () =>
      (telemetry?.zones || []).map((z, i) => ({
        label: t('zone', { zone: z.zone }),
        values: z.values,
        color: seriesColor(i),
      })),
    [telemetry, t],
  );

  const radarAxes = useMemo(
    () => (telemetry?.radar?.axes || []).map((key) => ({ label: t(`radarAxes.${key}`) })),
    [telemetry, t],
  );

  const fieldItems = useMemo(
    () =>
      (telemetry?.items || []).map((item) => ({
        id: item.key,
        label: t(`fields.${item.key}`),
        value: item.value,
        progress: item.progress,
      })),
    [telemetry, t],
  );

  return (
    <DashboardFrame role="user" activeKey="overview">
      <PageHead
        title={user?.name ? `${t('user.welcome')}, ${user.name}` : t('user.welcome')}
        subtitle={telemetry?.simulated ? t('common.simulated') : t('user.subtitle')}
        actions={
          <>
            <Button variant="primary" icon={<Plus size={15} strokeWidth={2.4} />}>
              {t('nav.invoices')}
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
          spark={telemetry?.week?.moisture}
        />
        <StatCard
          span={3}
          title={t('stats.outstanding')}
          value={stats ? `₹${stats.moisture}K` : '—'}
          loading={loading}
          icon={<Icon as={STAT_ICONS.receivable} />}
          trend={trend(stats?.moistureTrend)}
        />
        <StatCard
          span={3}
          title={t('stats.overdue')}
          value={stats?.temperature ?? '—'}
          loading={loading}
          icon={<Icon as={STAT_ICONS.overdue} />}
          trend={trend(stats?.temperatureTrend)}
        />
        <StatCard
          span={3}
          title={t('stats.paidThisYear')}
          value={stats ? `₹${stats.health}K` : '—'}
          loading={loading}
          icon={<Icon as={STAT_ICONS.payments} />}
          trend={trend(stats?.healthTrend)}
        />

        {/* ---------------- six-month bar chart ---------------- */}
        <Card span={6}>
          <CardHead
            title={t('charts.analytics')}
            subtitle={t('charts.analyticsSub')}
            action={<Button variant="subtle" size="sm" shape="rounded">{t('common.thisYear')}</Button>}
          />
          <CardBody>
            <BarChart
              data={analytics}
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
                { name: t('series.temperature'), data: telemetry?.week?.temperature || [], color: seriesColor(4), dashed: true },
              ]}
              height={190}
              ariaLabel={t('charts.weekly')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

        {/* ---------------- radial rings ---------------- */}
        <Card span={3}>
          <CardHead title={t('charts.indices')} />
          <CardBody>
            <RadialGauge
              rings={rings}
              size={158}
              showLegend
              ariaLabel={t('charts.indices')}
            />
          </CardBody>
        </Card>

        {/* ---------------- field node list ---------------- */}
        <ListCard
          span={4}
          title={t('user.mySensors')}
          items={fieldItems}
          loading={loading}
          emptyLabel={t('common.noData')}
          action={<Button variant="subtle" size="sm" shape="rounded">{t('common.viewAll')}</Button>}
        />

        {/* ---------------- distribution + profile ---------------- */}
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

        <Card span={6}>
          <CardHead title={t('charts.radar')} subtitle={t('charts.radarSub')} />
          <CardBody>
            <RadarChart
              axes={radarAxes}
              series={[
                { name: t('series.current'), data: telemetry?.radar?.current || [] },
                { name: t('series.target'), data: telemetry?.radar?.target || [], color: seriesColor(4) },
              ]}
              size={250}
              ariaLabel={t('charts.radar')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>

        {/* ---------------- activity + correlation ---------------- */}
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
          <CardHead title={t('charts.plots')} subtitle={t('charts.plotsSub')} />
          <CardBody>
            <ScatterPlot
              series={[{ name: t('charts.plots'), points: telemetry?.plots || [] }]}
              height={222}
              xLabel={t('series.moisture')}
              yLabel={t('radarAxes.yield')}
              ariaLabel={t('charts.plots')}
              emptyLabel={t('common.noData')}
            />
          </CardBody>
        </Card>
      </div>
      )}
    </DashboardFrame>
  );
}

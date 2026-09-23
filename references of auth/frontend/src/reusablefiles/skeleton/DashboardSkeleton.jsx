'use client';

// ============================================================
// FILE: src/reusablefiles/skeleton/DashboardSkeleton.jsx
//
// First-load placeholder for the dashboard grid.
//
// It renders the REAL <Card> components inside the REAL .dash-grid with
// the REAL span classes, and only swaps the contents for bars. That is
// what makes the swap to live data land without a reflow: the card
// borders, radii, padding and column spans are not approximated here,
// they are the same components the loaded page uses.
//
//   layout="farm"      user + manager consoles
//   layout="directory" admin + super-admin consoles
// ============================================================

import React from 'react';
import Card from '@/reusablefiles/card/Card';
import Skeleton, { SkeletonCardHead } from './Skeleton';

/** Mirrors StatCard: title row + icon, big value, spark, trend line. */
function StatSkeleton({ span = 3, tone = 'light' }) {
  return (
    <Card tone={tone} span={span} className="ui-stat">
      <div className="ui-stat-top">
        <Skeleton w="52%" h={11} />
        <Skeleton variant="circle" w={26} />
      </div>
      <Skeleton w="42%" h={26} radius={8} style={{ marginBottom: 6 }} />
      <div className="ui-stat-spark">
        <Skeleton w="100%" h={26} radius={0} />
      </div>
      <Skeleton w="70%" h={9} />
    </Card>
  );
}

/** Mirrors a chart card: head, then a plot area of the given height. */
function ChartSkeleton({ span, height, action = false }) {
  return (
    <Card span={span}>
      <SkeletonCardHead action={action} />
      <div className="ui-card-body">
        <Skeleton w="100%" h={height} radius={10} />
      </div>
    </Card>
  );
}

/** Mirrors a radial/gauge card: head, then a centred disc. */
function GaugeSkeleton({ span = 3, size = 158 }) {
  return (
    <Card span={span}>
      <SkeletonCardHead withSubtitle={false} />
      <div className="ui-card-body" style={{ display: 'grid', justifyItems: 'center', gap: 12 }}>
        <Skeleton variant="circle" w={size} />
        <Skeleton w="64%" h={9} />
      </div>
    </Card>
  );
}

/** Mirrors ListCard: head with an action, then divided rows. */
function ListSkeleton({ span = 4, rows = 4 }) {
  return (
    <Card span={span} className="ui-list-card">
      <SkeletonCardHead withSubtitle={false} action />
      <div className="ui-list ui-list-split is-divided">
        {Array.from({ length: rows }, (_, i) => (
          <div className="ui-list-row" key={i}>
            <span className="ui-list-text" style={{ width: '100%' }}>
              <Skeleton w={`${72 - i * 6}%`} h={10} />
            </span>
            <Skeleton w={38} h={10} />
          </div>
        ))}
      </div>
    </Card>
  );
}

/** Mirrors DataTable inside a card: header row plus body rows. */
function TableSkeleton({ span = 12, rows = 5, cols = 5 }) {
  return (
    <Card span={span}>
      <SkeletonCardHead withSubtitle={false} action />
      <div className="ui-card-body">
        <div className="table-wrap-dash">
          <table className="table-dash">
            <thead>
              <tr>
                {Array.from({ length: cols }, (_, c) => (
                  <th key={c}><Skeleton w="58%" h={9} /></th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: rows }, (_, r) => (
                <tr key={r}>
                  {Array.from({ length: cols }, (_, c) => (
                    <td key={c}>
                      <Skeleton w={c === 0 ? '70%' : c === cols - 1 ? '46%' : '82%'} h={9} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  );
}

export default function DashboardSkeleton({ layout = 'farm' }) {
  const directory = layout === 'directory';

  return (
    <div className="dash-grid" aria-busy="true">
      <StatSkeleton tone="deep" />
      <StatSkeleton />
      <StatSkeleton />
      <StatSkeleton />

      {directory ? (
        <>
          <ChartSkeleton span={6} height={206} />
          <GaugeSkeleton span={3} />
          <GaugeSkeleton span={3} />
          <ChartSkeleton span={6} height={206} />
          <ChartSkeleton span={6} height={206} />
          <TableSkeleton span={12} />
        </>
      ) : (
        <>
          <ChartSkeleton span={6} height={206} action />
          <GaugeSkeleton span={3} />
          <Card tone="deep" span={3} className="ui-tracker">
            <div className="ui-tracker-inner">
              <Skeleton w="46%" h={12} />
              <div className="ui-tracker-read">
                <Skeleton w="66%" h={26} radius={8} />
                <Skeleton w="52%" h={9} />
              </div>
              <div className="ui-tracker-controls">
                <Skeleton variant="circle" w={42} />
                <Skeleton variant="circle" w={42} />
              </div>
            </div>
          </Card>

          <ChartSkeleton span={5} height={190} />
          <GaugeSkeleton span={3} />
          <ListSkeleton span={4} />

          <ChartSkeleton span={6} height={222} />
          <ChartSkeleton span={6} height={222} />
        </>
      )}
    </div>
  );
}

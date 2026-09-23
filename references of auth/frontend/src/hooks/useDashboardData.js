'use client';

// ============================================================
// FILE: src/hooks/useDashboardData.js
//
// One hook the four dashboards share. It owns the fetch lifecycle
// (loading / error / refresh) and hands back data already shaped by
// `@/services/dashboard.service`, so the pages contain layout only.
//
//   const { loading, error, users, metrics, refresh } =
//     useDashboardData({ scope: 'directory' });
//
// scopes:
//   'directory'  — user rows + derived role/signup/verification metrics
//   'farm'       — field telemetry for the farmer dashboard
//   'operations' — regional telemetry + manager summary
// ============================================================

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  buildDirectoryMetrics,
  fetchFarmTelemetry,
  fetchManagerSummary,
  fetchUsers,
} from '@/services/dashboard.service';

/**
 * Pure fetch for one scope. Returns a payload — it never touches state,
 * which is what lets both the mount effect and the refresh button drive
 * it without duplicating the request logic.
 */
async function fetchScope(scope) {
  if (scope === 'directory') {
    const res = await fetchUsers();
    return { users: res.users, error: res.error };
  }

  if (scope === 'operations') {
    const [telemetry, mgr] = await Promise.all([
      fetchFarmTelemetry('operations'),
      fetchManagerSummary(),
    ]);
    return { telemetry, summary: mgr.summary, error: mgr.error };
  }

  return { telemetry: await fetchFarmTelemetry('farm'), error: null };
}

export default function useDashboardData({ scope = 'farm', enabled = true } = {}) {
  const [state, setState] = useState({
    users: [],
    telemetry: null,
    summary: null,
    error: null,
    loading: enabled,
  });

  // Applies a payload, or an unexpected failure, as one state update.
  const apply = useCallback((payload) => {
    setState({
      users: payload.users || [],
      telemetry: payload.telemetry || null,
      summary: payload.summary || null,
      error: payload.error || null,
      loading: false,
    });
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;

    let cancelled = false;

    fetchScope(scope)
      .then((payload) => { if (!cancelled) apply(payload); })
      .catch((err) => {
        if (!cancelled) apply({ error: err?.message || 'Failed to load dashboard' });
      });

    return () => { cancelled = true; };
  }, [scope, enabled, apply]);

  /** Re-runs the same fetch — safe to hand straight to a button. */
  const refresh = useCallback(async () => {
    if (!enabled) return;
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      apply(await fetchScope(scope));
    } catch (err) {
      apply({ error: err?.message || 'Failed to load dashboard' });
    }
  }, [scope, enabled, apply]);

  // Recomputed only when the rows change, not on every render.
  const metrics = useMemo(
    () => (scope === 'directory' ? buildDirectoryMetrics(state.users) : null),
    [scope, state.users],
  );

  return {
    loading: state.loading,
    error: state.error,
    users: state.users,
    telemetry: state.telemetry,
    summary: state.summary,
    metrics,
    refresh,
  };
}

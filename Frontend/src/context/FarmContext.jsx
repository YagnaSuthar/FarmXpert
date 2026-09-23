'use client';

// ============================================================
// FILE: src/context/FarmContext.jsx
// The farm (and field) the dashboard is looking at. Most farmers have
// one; the switcher appears only when there is more than one. The
// choice is remembered on this device.
// ============================================================

import { createContext, useCallback, useContext, useMemo, useState } from 'react';

import { useApi } from '@/hooks/useApi';

const FarmContext = createContext(null);
const KEY = 'fx.farm';

function remembered() {
  try { return window.localStorage.getItem(KEY); } catch { return null; }
}

export function FarmProvider({ children }) {
  const farms = useApi('/farms');
  const [chosen, setChosen] = useState(() => (typeof window === 'undefined' ? null : remembered()));
  const items = useMemo(() => farms.data?.items || [], [farms.data]);

  // The chosen farm if it still exists, else the most recent one.
  const farm = items.find((f) => f.id === chosen) || items[0] || null;
  const fields = useApi(farm ? `/farms/${farm.id}/fields` : null);
  const field = fields.data?.items?.[0] || null;

  const setFarmId = useCallback((id) => {
    setChosen(id);
    try { window.localStorage.setItem(KEY, id); } catch { /* per-device convenience only */ }
  }, []);

  const { reload: reloadFarms } = farms;
  const { reload: reloadFields } = fields;
  const reload = useCallback(() => { reloadFarms(); reloadFields(); }, [reloadFarms, reloadFields]);

  const value = useMemo(() => ({
    farms: items, farm, field, fields: fields.data?.items || [],
    loading: farms.loading || Boolean(farm && fields.loading), setFarmId, reload,
  }), [items, farm, field, fields.data, farms.loading, fields.loading, setFarmId, reload]);

  return <FarmContext.Provider value={value}>{children}</FarmContext.Provider>;
}

export function useFarm() {
  const ctx = useContext(FarmContext);
  if (!ctx) throw new Error('useFarm must be used inside <FarmProvider>');
  return ctx;
}

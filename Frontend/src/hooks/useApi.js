'use client';

// ============================================================
// FILE: src/hooks/useApi.js
// A small data hook: cached by key, so returning to a page shows the
// last data at once and refreshes it quietly (stale-while-revalidate).
// `null` as the key means "not yet" (e.g. waiting for a farm id).
// ============================================================

import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '@/lib/api';

const cache = new Map();
const fresh = (key) => ({ key, data: key ? cache.get(key) : undefined, error: null, loading: Boolean(key) && !cache.has(key) });

export function useApi(path, { enabled = true } = {}) {
  const key = enabled ? path : null;
  const [state, setState] = useState(() => fresh(key));
  const alive = useRef(true);

  // A new key resets the state during render - React's pattern for state
  // derived from props, which avoids a flash of the previous key's data.
  if (state.key !== key) setState(fresh(key));

  const load = useCallback(async () => {
    if (!key) return undefined;
    try {
      const data = await api.get(key);
      cache.set(key, data);
      if (alive.current) setState((s) => (s.key === key ? { key, data, error: null, loading: false } : s));
      return data;
    } catch (error) {
      if (alive.current) setState((s) => (s.key === key ? { ...s, error, loading: false } : s));
      return undefined;
    }
  }, [key]);

  useEffect(() => {
    alive.current = true;
    load();
    return () => { alive.current = false; };
  }, [load]);

  const mutate = useCallback((updater) => {
    setState((s) => {
      const data = typeof updater === 'function' ? updater(s.data) : updater;
      if (key) cache.set(key, data);
      return { ...s, data };
    });
  }, [key]);

  return { data: state.data, error: state.error, loading: state.loading, reload: load, mutate };
}

/** Forget cached responses (after sign-out, or a change that affects many pages). */
export function clearApiCache(prefix) {
  for (const k of cache.keys()) if (!prefix || k.startsWith(prefix)) cache.delete(k);
}

'use client';

// ============================================================
// FILE: src/context/AuthContext.jsx
//
// The signed-in farmer, for the whole app.
//
// On load the session is restored with one silent refresh (the
// HttpOnly cookie proves who you are); nothing is read from
// localStorage. `status` is 'loading' until that answer arrives, so
// guarded pages show a skeleton instead of flashing the login form.
// ============================================================

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { api, onSessionEnd, refreshSession, setAccessToken } from '@/lib/api';

// One instance per page, even if hot reload or chunking evaluates this module
// twice - otherwise the provider and its consumers hold different contexts.
const AuthContext = globalThis.__fxAuthContext ??= createContext(null);

// One restore per page load, even under React's double-invoked effects.
let restoring = null;

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    let alive = true;
    restoring ??= refreshSession();
    restoring.then((session) => {
      if (!alive) return;
      setUser(session?.user ?? null);
      setStatus(session?.user ? 'authenticated' : 'anonymous');
    });
    const off = onSessionEnd(() => {
      setUser(null);
      setStatus('anonymous');
    });
    return () => {
      alive = false;
      off();
    };
  }, []);

  const login = useCallback(async (credentials) => {
    const session = await api.post('/auth/login', credentials);
    setAccessToken(session.access_token);
    setUser(session.user);
    setStatus('authenticated');
    return session.user;
  }, []);

  const logout = useCallback(async ({ everywhere = false } = {}) => {
    try {
      await api.post(everywhere ? '/auth/logout-everywhere' : '/auth/logout');
    } catch {
      /* the cookie is cleared server-side; nothing else to do */
    }
    setAccessToken(null);
    restoring = null;
    setUser(null);
    setStatus('anonymous');
  }, []);

  const reload = useCallback(async () => {
    const { user: fresh } = await api.get('/auth/me');
    setUser(fresh);
    return fresh;
  }, []);

  const value = useMemo(() => ({ user, status, login, logout, reload, setUser }),
    [user, status, login, logout, reload]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import api, { setToken, clearToken, getToken } from '@/lib/api';

/**
 * AuthContext
 *
 * Source of truth: GET /api/auth/me
 *
 * State:
 *   user        — server-returned user object (id, name, email, role, email_verified, created_at)
 *   loading     — true while initial auth check is in progress
 *   isAuthenticated — derived from user presence
 *
 * Security rules:
 *   - Role comes ONLY from /me response, never from localStorage/URL/hidden fields
 *   - JWT stored in-memory only (React ref), never persisted
 *   - Privileged roles use HttpOnly session cookie (browser handles automatically)
 *   - This is a UX layer; backend RBAC is the real security boundary
 */

const defaultAuthValue = {
  user: null,
  loading: true,
  isAuthenticated: false,
  role: null,
  login: async () => ({ success: false }),
  logout: async () => {},
  refreshUser: async () => {},
};

const AuthContext = createContext(defaultAuthValue);

// Module-level single-flight lock for initAuth.
// Prevents React 18 Strict Mode from double-firing /auth/refresh
// which would trigger the backend's token reuse detection.
let _initAuthPromise = null;

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const tokenRef = useRef(getToken());

  /**
   * Fetch authenticated user profile from backend.
   * Sets user state from server-authoritative response.
   */
  const fetchUser = useCallback(async () => {
    try {
      const res = await api.get('/auth/me');
      if (res.success && res.data?.user) {
        setUser(res.data.user);
      } else {
        setUser(null);
        clearToken();
      }
    } catch {
      setUser(null);
      clearToken();
    }
  }, []);

  // Module-level single-flight promise for initAuth.
  // React 18 Strict Mode double-fires useEffect: mount → unmount → mount.
  // Without deduplication, the first mount calls /auth/refresh and ROTATES the
  // token (old revoked, new issued). The second mount sends the same old cookie
  // before the browser processes the Set-Cookie from the first response.
  // The backend then sees a revoked token → reuse detection → ALL tokens revoked.
  // By sharing a single promise, both mounts await the same API call.

  useEffect(() => {
    let ignore = false;

    async function initAuth() {
      try {
        // Single-flight: reuse in-progress promise if Strict Mode fires again
        if (!_initAuthPromise) {
          _initAuthPromise = (async () => {
            // Attempt silent refresh for standard user
            try {
              const refreshRes = await api.post('/auth/refresh');
              if (refreshRes.success && refreshRes.data?.token) {
                return {
                  token: refreshRes.data.token,
                  user: refreshRes.data.user || null,
                };
              }
            } catch {
              // Refresh cookie not present or invalid; proceed to check session
            }

            // Check /me (works for active privileged sid sessions)
            try {
              const meRes = await api.get('/auth/me');
              if (meRes.success && meRes.data?.user) {
                return { user: meRes.data.user };
              }
            } catch {
              // Not authenticated
            }

            return null;
          })();
        }

        const result = await _initAuthPromise;

        if (!ignore) {
          if (result?.token) {
            setToken(result.token);
            tokenRef.current = result.token;
          }
          if (result?.user) {
            setUser(result.user);
          } else {
            setUser(null);
            clearToken();
          }
        }
      } finally {
        _initAuthPromise = null;
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    initAuth();

    // Listen for pageshow (bfcache restoration when user clicks back after logout)
    const handlePageShow = (event) => {
      if (event.persisted) {
        window.location.reload();
      }
    };
    window.addEventListener('pageshow', handlePageShow);

    return () => {
      ignore = true;
      window.removeEventListener('pageshow', handlePageShow);
    };
  }, []);

  /**
   * Login: POST /api/auth/login
   * Stores JWT in memory for 'user' role.
   * Privileged roles get HttpOnly session cookie automatically.
   *
   * @param {object} credentials - { email, password, captchaId, captchaAnswer }
   * @returns {object} - { user } from server response
   */
  const login = useCallback(async (credentials) => {
    const res = await api.post('/auth/login', credentials);

    // If backend returned a JWT (user role), store in memory
    if (res.data?.token) {
      setToken(res.data.token);
      tokenRef.current = res.data.token;
    }

    // Always fetch fresh user from /me (server-authoritative role)
    if (res.data?.user) {
      setUser(res.data.user);
    } else {
      await fetchUser();
    }
    setLoading(false);

    return res;
  }, [fetchUser]);

  /**
   * Logout: POST /api/auth/logout
   * Backend invalidates session. Frontend clears state and replaces URL to prevent back-navigation.
   */
  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout');
    } catch {
      // Even if logout request fails, clear local state
    }
    setUser(null);
    clearToken();
    tokenRef.current = null;
    setLoading(false);

    if (typeof window !== 'undefined') {
      window.location.replace('/auth/login');
    }
  }, []);

  /**
   * Refresh user state from /me.
   * Useful after email verification, role changes, etc.
   */
  const refreshUser = useCallback(async () => {
    await fetchUser();
  }, [fetchUser]);

  const value = {
    user,
    loading,
    isAuthenticated: !!user,
    role: user?.role || null,
    login,
    logout,
    refreshUser,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Hook to access auth context.
 * Must be used within AuthProvider.
 */
export function useAuth() {
  const context = useContext(AuthContext);
  return context || defaultAuthValue;
}

/**
 * Get the correct dashboard path for a given role.
 * @param {string} role
 * @returns {string}
 */
export function getDashboardPath(role) {
  switch (role) {
    case 'manager':
      return '/dashboard/manager';
    case 'admin':
      return '/dashboard/admin';
    case 'super_admin':
      return '/dashboard/super-admin';
    case 'user':
    default:
      return '/dashboard/user';
  }
}

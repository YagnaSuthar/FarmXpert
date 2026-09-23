// ============================================================
// FILE: src/lib/api.js
//
// Every call to the FarmXpert backend goes through here.
//
// Tokens (the reference auth design):
//   - The 15-minute access token lives in memory only - never in
//     localStorage, where any injected script could read it.
//   - The refresh token is an HttpOnly cookie the browser sends to
//     /api/v1/auth/* by itself; this code never sees it.
//   - A 401 triggers one silent refresh, shared by every request that
//     hit it at the same moment, then the request is retried once.
// ============================================================

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000').replace(/\/+$/, '');

let accessToken = null;
let refreshing = null;
const listeners = new Set();

export const getAccessToken = () => accessToken;
export function setAccessToken(token) {
  accessToken = token || null;
}
/** Called when the session ends (refresh refused), so the app can go to login. */
export function onSessionEnd(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/** One refresh at a time; everyone waiting gets the same result. */
export function refreshSession() {
  refreshing ??= (async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/auth/refresh`, { method: 'POST', credentials: 'include' });
      if (!res.ok) {
        setAccessToken(null);
        return null;
      }
      const body = await res.json();
      setAccessToken(body.access_token);
      return body;
    } catch {
      return null;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

const AUTH_PUBLIC = /^\/auth\/(login|register|refresh|captcha|verify-email|resend-code|forgot-password|verify-reset-code|reset-password|logout)/;

/**
 * fetch() against /api/v1 with auth, JSON and errors handled.
 * Throws ApiError { status, code, message, details } on failure.
 */
export async function api(path, { method = 'GET', body, headers = {}, signal, raw = false, retry = true } = {}) {
  const init = {
    method,
    signal,
    // Cookies only go to the auth routes (the refresh cookie's path anyway).
    credentials: path.startsWith('/auth/') ? 'include' : 'same-origin',
    headers: {
      ...(body !== undefined && !(body instanceof Blob) ? { 'Content-Type': 'application/json' } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
    body: body === undefined ? undefined : body instanceof Blob ? body : JSON.stringify(body),
  };
  const res = await fetch(`${API_URL}/api/v1${path}`, init);

  if (res.status === 401 && retry && !AUTH_PUBLIC.test(path)) {
    const renewed = await refreshSession();
    if (renewed) return api(path, { method, body, headers, signal, raw, retry: false });
    listeners.forEach((fn) => fn());
  }
  if (raw) return res;
  if (res.status === 204) return null;

  let data = null;
  try {
    data = await res.json();
  } catch {
    /* empty or not JSON */
  }
  if (!res.ok) {
    throw new ApiError(res.status, data?.error?.code || 'request_failed',
      data?.error?.message || 'Something went wrong. Please try again.', data?.error?.details);
  }
  return data;
}

api.get = (path, opts) => api(path, { ...opts, method: 'GET' });
api.post = (path, body, opts) => api(path, { ...opts, method: 'POST', body });
api.patch = (path, body, opts) => api(path, { ...opts, method: 'PATCH', body });
api.delete = (path, opts) => api(path, { ...opts, method: 'DELETE' });

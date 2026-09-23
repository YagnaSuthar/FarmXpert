/**
 * Centralized API Client
 *
 * - Prepends NEXT_PUBLIC_API_URL
 * - JSON headers
 * - credentials: 'include' (for HttpOnly session & refresh cookies)
 * - Authorization header for JWT (user role, memory-only)
 * - Single-flight refresh token lock (prevents concurrent refresh races)
 * - Automatic retry after refresh
 * - Unified error parsing
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000/api';

/**
 * In-memory JWT store. Never persisted to localStorage/sessionStorage.
 * Only used for 'user' role authentication (short-lived 15m JWT).
 * Privileged roles (manager/admin/super_admin) rely on HttpOnly session cookies.
 */
let _token = null;
let _refreshPromise = null;

export function setToken(token) {
  _token = token;
}

export function getToken() {
  return _token;
}

export function clearToken() {
  _token = null;
}

/**
 * Single-flight token refresh.
 * Ensures that multiple concurrent 401 requests trigger only ONE /auth/refresh call.
 */
async function performTokenRefresh() {
  if (!_refreshPromise) {
    _refreshPromise = (async () => {
      try {
        const config = {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
        };
        const res = await fetch(`${BASE_URL}/auth/refresh`, config);
        const json = await res.json().catch(() => ({}));
        if (res.ok && json.success && json.data?.token) {
          setToken(json.data.token);
          return json.data.token;
        }
        clearToken();
        return null;
      } catch {
        clearToken();
        return null;
      } finally {
        _refreshPromise = null;
      }
    })();
  }
  return _refreshPromise;
}

/**
 * Core fetch wrapper.
 *
 * @param {string} endpoint - API path (e.g. '/auth/login')
 * @param {object} options
 * @param {string} [options.method='GET']
 * @param {object} [options.body]
 * @param {object} [options.headers]
 * @param {boolean} [options._isRetry=false]
 * @returns {Promise<{ success: boolean, message: string, data?: any, errors?: string[] }>}
 */
export async function apiFetch(endpoint, { method = 'GET', body, headers = {}, _isRetry = false } = {}) {
  const config = {
    method,
    credentials: 'include', // Always include cookies for session & refresh token auth
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
  };

  // Attach JWT for user-role requests (memory-only)
  if (_token) {
    config.headers['Authorization'] = `Bearer ${_token}`;
  }

  if (body && method !== 'GET') {
    config.body = JSON.stringify(body);
  }

  const res = await fetch(`${BASE_URL}${endpoint}`, config);

  // Handle 401 with transparent refresh (once, unless this is already login/refresh/logout/retry)
  const isAuthEndpoint =
    endpoint.startsWith('/auth/login') ||
    endpoint.startsWith('/auth/refresh') ||
    endpoint.startsWith('/auth/logout');

  if (res.status === 401 && !_isRetry && !isAuthEndpoint) {
    const newToken = await performTokenRefresh();
    if (newToken) {
      return apiFetch(endpoint, { method, body, headers, _isRetry: true });
    }
  }

  // Parse JSON response
  let json;
  try {
    json = await res.json();
  } catch {
    throw {
      success: false,
      status: res.status,
      message: 'Unexpected server response',
      errors: [],
    };
  }

  if (!res.ok) {
    throw {
      success: false,
      status: res.status,
      message: json.message || 'Something went wrong',
      errors: json.errors || [],
    };
  }

  return json;
}

/** Convenience helpers */
const api = {
  get: (endpoint, opts) => apiFetch(endpoint, { method: 'GET', ...opts }),
  post: (endpoint, body, opts) => apiFetch(endpoint, { method: 'POST', body, ...opts }),
  patch: (endpoint, body, opts) => apiFetch(endpoint, { method: 'PATCH', body, ...opts }),
  delete: (endpoint, opts) => apiFetch(endpoint, { method: 'DELETE', ...opts }),
};

export default api;


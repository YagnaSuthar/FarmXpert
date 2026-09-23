/**
 * Per-client request rate limit (sliding window; one minute unless told otherwise).
 *
 * The daily token and voice allowances (modules/usage.js) are the real cost
 * guard; this stops bursts - a stuck retry loop or a script hammering the
 * AI - before they reach the database or cost a model call. In memory and
 * per process: with N instances behind a balancer the effective limit is up
 * to N times this, which is fine for a burst guard. A shared limit would move
 * this to Redis.
 *
 * Keyed by the signed-in user, else by client IP (behind the balancer,
 * `trust proxy` makes req.ip the real client).
 */

import { HttpError } from './errors.js';

export function rateLimit({ perMinute, limit = perMinute, windowMs = 60_000, name }) {
  const hits = new Map();          // key -> timestamps within the window
  const WINDOW = windowMs;

  // Forget idle clients so the map cannot grow without bound.
  const sweep = setInterval(() => {
    const cutoff = Date.now() - WINDOW;
    for (const [key, times] of hits) {
      if (!times.length || times[times.length - 1] < cutoff) hits.delete(key);
    }
  }, WINDOW);
  sweep.unref();

  return function limiter(req, res, next) {
    if (!limit) return next();
    // Only a verified identity: a user id in the body could be varied to dodge the limit.
    const key = req.user?.id ? `u:${req.user.id}` : `ip:${req.ip}`;
    const now = Date.now();
    const times = (hits.get(key) || []).filter((t) => t > now - WINDOW);
    if (times.length >= limit) {
      const retryAfter = Math.max(1, Math.ceil((times[0] + WINDOW - now) / 1000));
      res.set('Retry-After', String(retryAfter));
      return next(new HttpError(429, 'rate_limited',
        'Too many questions at once. Please wait a moment.', { retry_after_s: retryAfter, limit: name }));
    }
    times.push(now);
    hits.set(key, times);
    return next();
  };
}

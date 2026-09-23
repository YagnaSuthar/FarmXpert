import { timingSafeEqual } from 'node:crypto';

import { Router } from 'express';

import { config } from '../config/env.js';
import { query } from '../db/pool.js';
import { HttpError, unauthorized } from '../lib/errors.js';
import { jobs, withJobLock } from '../jobs/scheduler.js';
import { authenticate, requireRole } from './auth/middleware.js';

export const adminRoutes = Router();

/**
 * Admin access: an admin account's access token (the dashboard), or the
 * x-admin-key (scripts and cron). Either is enough; neither is refused.
 */
export async function requireAdmin(req, res, next) {
  if ((req.get('authorization') || '').startsWith('Bearer ')) {
    return authenticate(req, res, (err) => {
      if (err) return next(err);
      return requireRole('admin', 'super_admin')(req, res, next);
    });
  }
  const supplied = Buffer.from(req.get('x-admin-key') || '');
  const expected = Buffer.from(config.adminKey);
  if (!expected.length) return next(new HttpError(503, 'admin_disabled', 'ADMIN_API_KEY is not configured.'));
  if (supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) return next(unauthorized());
  return next();
}

adminRoutes.use('/admin', requireAdmin);

for (const name of Object.keys(jobs)) {
  adminRoutes.post(`/admin/jobs/${name}`, async (req, res) => {
    const result = await withJobLock(name, jobs[name]);
    if (result === null) throw new HttpError(409, 'job_running', `The ${name} job is already running.`);
    res.json({ job: name, result });
  });
}

adminRoutes.get('/admin/archive', async (req, res) => {
  const { rows } = await query(
    `SELECT table_name, partition_name, range_start, range_end, uri, row_count, bytes, sha256,
            status, error, started_at, finished_at
       FROM archive_manifest ORDER BY range_start DESC LIMIT 200`,
  );
  res.json({ items: rows });
});

// Table sizes, so storage growth is visible without a database console.
adminRoutes.get('/admin/storage', async (req, res) => {
  const { rows } = await query(
    `SELECT p.relname AS table_name,
            COALESCE(sum(pg_total_relation_size(c.oid)), pg_total_relation_size(p.oid))::bigint AS bytes,
            count(c.oid)::int AS partitions
       FROM pg_class p
       LEFT JOIN pg_inherits i ON i.inhparent = p.oid
       LEFT JOIN pg_class c ON c.oid = i.inhrelid
      WHERE p.relnamespace = 'public'::regnamespace AND p.relkind IN ('r', 'p')
        AND NOT p.relispartition
      GROUP BY p.relname, p.oid
      ORDER BY bytes DESC`,
  );
  res.json({ items: rows });
});

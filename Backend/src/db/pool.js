/**
 * PostgreSQL connection pool (node-postgres).
 *
 * Raw SQL through `pg`, no ORM. An ORM adds work to every query and fights
 * exactly the features this schema depends on - PostGIS geography, pgvector,
 * partitioned tables and triggers. Hand-written SQL is both the fastest path
 * and the most readable one for this schema.
 *
 * Every connection gets a statement timeout and a lock timeout, so a runaway
 * query fails and frees its connection instead of starving the pool, and an
 * `idle_in_transaction` limit, so a crashed request cannot hold row locks.
 */

import pg from 'pg';

import { config } from '../config/env.js';
import { unavailable } from '../lib/errors.js';
import { logger } from '../lib/logger.js';

// NUMERIC (money, depths) arrives as a string by default so no precision is
// lost; BIGINT (counts) as well. Counts fit in a JS number, so parse those.
pg.types.setTypeParser(20, (value) => Number.parseInt(value, 10));
// DATE stays 'YYYY-MM-DD'. As a JS Date it becomes local midnight, which a
// server in UTC and a farmer in IST read as two different days.
pg.types.setTypeParser(1082, (value) => value);

let pool = null;

export function databaseConfigured() {
  return Boolean(config.db.url);
}

export function getPool() {
  if (pool) return pool;
  if (!config.db.url) throw unavailable('The database is not configured.');

  pool = new pg.Pool({
    connectionString: config.db.url,
    max: config.db.poolMax,
    idleTimeoutMillis: config.db.idleTimeoutMs,
    connectionTimeoutMillis: 5000,
    keepAlive: true,
    ssl: config.db.ssl === 'disable' ? false : { rejectUnauthorized: config.db.ssl === 'verify-full' },
    application_name: 'farmxpert-backend',
    statement_timeout: config.db.statementTimeoutMs,
    lock_timeout: 5000,
    idle_in_transaction_session_timeout: 30000,
  });
  // An idle client dying (a managed database scaling to zero) must not crash
  // the process; the pool replaces it on the next checkout.
  pool.on('error', (err) => logger.warn({ err }, 'Idle database client error'));
  return pool;
}

/** Run one statement. Logs slow queries, never their parameters. */
export async function query(text, params = []) {
  const started = performance.now();
  const result = await getPool().query(text, params);
  const ms = performance.now() - started;
  if (ms > 250) {
    logger.warn({ ms: Math.round(ms), sql: text.slice(0, 120) }, 'Slow query');
  }
  return result;
}

/** The first row, or null. */
export async function one(text, params) {
  const { rows } = await query(text, params);
  return rows[0] ?? null;
}

/**
 * Run `work(client)` in one transaction. Commits on success, rolls back on
 * any error and rethrows it, and always returns the client to the pool.
 */
export async function transaction(work) {
  const client = await getPool().connect();
  try {
    await client.query('BEGIN');
    const result = await work(client);
    await client.query('COMMIT');
    return result;
  } catch (err) {
    await client.query('ROLLBACK').catch(() => {});
    throw err;
  } finally {
    client.release();
  }
}

export async function closePool() {
  if (pool) {
    const closing = pool;
    pool = null;
    await closing.end();
  }
}

/**
 * Hot/cold lifecycle, run daily.
 *
 *  1. Create next months' partitions ahead of time, so an insert never lands
 *     in DEFAULT (which would block creating that month's partition later).
 *  2. For each retention policy, every monthly partition wholly older than
 *     its hot window is: exported -> finalised -> read back and verified
 *     (row count equal to the live count, checksum recorded) -> detached and
 *     dropped. Any failure leaves the partition in place and the manifest
 *     row 'failed'; the next run retries.
 *  3. Purge idempotency keys older than 48 hours, and daily token totals
 *     older than TOKEN_USAGE_RETENTION_DAYS.
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { config } from '../config/env.js';
import { getPool, query } from '../db/pool.js';
import { logger } from '../lib/logger.js';
import { purgeExpired as purgeAuth } from '../modules/auth/service.js';
import * as store from './archiveStore.js';

export const PARTITIONED = ['soil_data', 'messages', 'orchestration_requests', 'agent_outputs', 'weather_snapshots'];
const BATCH = 5000;

// Rows elsewhere that reference a partition and must go (archived) with it.
const DEPENDENTS = {
  soil_data: { table: 'soil_analyses', column: 'reading_recorded_at' },
};

/** Months (as 'YYYY_MM' partition suffixes) that are wholly older than the hot window. */
export function retirePlan(partitionNames, parent, hotMonths, now = new Date()) {
  const cutoff = Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - hotMonths, 1);
  const pattern = new RegExp(`^${parent}_(\\d{4})_(\\d{2})$`);
  return partitionNames
    .map((name) => {
      const m = pattern.exec(name);
      if (!m) return null;
      const start = new Date(Date.UTC(+m[1], +m[2] - 1, 1));
      const end = new Date(Date.UTC(+m[1], +m[2], 1));
      return end.getTime() <= cutoff ? { name, start, end } : null;
    })
    .filter(Boolean)
    .sort((a, b) => a.start - b.start);
}

export async function runLifecycle({ archiveUri = config.lifecycle.archiveUri, now = new Date() } = {}) {
  const report = { partitionsCreated: 0, archived: [], dropped: [], failed: [], idempotencyPurged: 0, tokenUsagePurged: 0 };

  for (const parent of PARTITIONED) {
    const { rows } = await query('SELECT farmxpert_rolling_partitions($1) AS n', [parent]);
    report.partitionsCreated += rows[0].n;
  }

  const { rows: policies } = await query(
    'SELECT table_name, hot_months, cold_action FROM retention_policies WHERE enabled',
  );
  for (const policy of policies) {
    if (!PARTITIONED.includes(policy.table_name)) continue;
    const { rows: parts } = await query(
      `SELECT c.relname FROM pg_inherits i
         JOIN pg_class c ON c.oid = i.inhrelid
         JOIN pg_class p ON p.oid = i.inhparent
        WHERE p.relname = $1`,
      [policy.table_name],
    );
    const plan = retirePlan(parts.map((p) => p.relname), policy.table_name, policy.hot_months, now);
    for (const part of plan) {
      try {
        if (policy.cold_action === 'drop') {
          await dropPartition(policy.table_name, part, null);
          report.dropped.push(part.name);
        } else {
          await archivePartition(policy.table_name, part, archiveUri);
          report.archived.push(part.name);
        }
      } catch (err) {
        logger.error({ err, partition: part.name }, 'Lifecycle failed for partition; left in place');
        await query(
          `UPDATE archive_manifest SET status = 'failed', error = $2, finished_at = now()
            WHERE partition_name = $1 AND status <> 'dropped'`,
          [part.name, String(err.message).slice(0, 500)],
        ).catch(() => {});
        report.failed.push(part.name);
      }
    }
  }

  const purged = await query("DELETE FROM idempotency_keys WHERE created_at < now() - interval '48 hours'");
  report.idempotencyPurged = purged.rowCount;
  const usage = await query(
    'DELETE FROM token_usage_daily WHERE usage_date < CURRENT_DATE - $1::int',
    [config.tokens.retentionDays],
  );
  report.tokenUsagePurged = usage.rowCount;
  // Spent codes, captchas and old refresh tokens.
  report.authPurged = await purgeAuth();
  logger.info(report, 'Storage lifecycle finished');
  return report;
}

async function archivePartition(parent, part, archiveUri) {
  await query(
    `INSERT INTO archive_manifest (table_name, partition_name, range_start, range_end, status)
     VALUES ($1, $2, $3, $4, 'exporting')
     ON CONFLICT (partition_name) DO UPDATE SET status = 'exporting', error = NULL, started_at = now()`,
    [parent, part.name, part.start, part.end],
  );

  const files = [await exportRows(archiveUri, parent, part.name, `SELECT * FROM ${ident(part.name)}`, [])];
  const dependent = DEPENDENTS[parent];
  if (dependent) {
    files.push(await exportRows(
      archiveUri, parent, `${part.name}__${dependent.table}`,
      `SELECT * FROM ${ident(dependent.table)} WHERE ${ident(dependent.column)} >= $1 AND ${ident(dependent.column)} < $2`,
      [part.start, part.end],
    ));
  }

  // Verify: the file as stored must hold exactly what the database holds now.
  // Nothing writes to a month this old, so a mismatch means a broken export.
  const [main] = files;
  const live = await query(`SELECT count(*)::bigint AS n FROM ${ident(part.name)}`);
  if (live.rows[0].n !== main.rows) {
    throw new Error(`Export of ${part.name} holds ${main.rows} rows, the partition ${live.rows[0].n}`);
  }

  await query(
    `UPDATE archive_manifest SET status = 'verified', uri = $2, row_count = $3, bytes = $4, sha256 = $5
      WHERE partition_name = $1`,
    [part.name, main.uri, main.rows, files.reduce((s, f) => s + f.bytes, 0), main.sha256],
  );
  await dropPartition(parent, part, main.uri);
}

async function exportRows(archiveUri, table, name, sql, params) {
  const writer = await store.open(archiveUri, table, name);
  const client = await getPool().connect();
  try {
    // A server-side cursor: memory stays flat however large the month is.
    await client.query('BEGIN READ ONLY');
    await client.query(`DECLARE archive_cursor NO SCROLL CURSOR FOR ${sql}`, params);
    for (;;) {
      const { rows } = await client.query(`FETCH ${BATCH} FROM archive_cursor`);
      for (const row of rows) await writer.write(row);
      if (rows.length < BATCH) break;
    }
    await client.query('COMMIT');
    const written = await writer.close();
    const { uri, bytes } = await store.finalize(writer);
    const check = await store.verify(writer.finalPath);
    if (check.rows !== written) {
      throw new Error(`Read-back of ${name} found ${check.rows} rows, wrote ${written}`);
    }
    return { uri, bytes, rows: written, sha256: check.sha256 };
  } catch (err) {
    await client.query('ROLLBACK').catch(() => {});
    await store.discard(writer).catch(() => {});
    throw err;
  } finally {
    client.release();
  }
}

async function dropPartition(parent, part, uri) {
  const client = await getPool().connect();
  try {
    await client.query('BEGIN');
    const dependent = DEPENDENTS[parent];
    if (dependent) {
      await client.query(
        `DELETE FROM ${ident(dependent.table)} WHERE ${ident(dependent.column)} >= $1 AND ${ident(dependent.column)} < $2`,
        [part.start, part.end],
      );
    }
    await client.query(`ALTER TABLE ${ident(parent)} DETACH PARTITION ${ident(part.name)}`);
    await client.query(`DROP TABLE ${ident(part.name)}`);
    await client.query(
      `INSERT INTO archive_manifest (table_name, partition_name, range_start, range_end, uri, status, finished_at)
       VALUES ($1, $2, $3, $4, $5, 'dropped', now())
       ON CONFLICT (partition_name) DO UPDATE SET status = 'dropped', finished_at = now()`,
      [parent, part.name, part.start, part.end, uri],
    );
    await client.query('COMMIT');
  } catch (err) {
    await client.query('ROLLBACK').catch(() => {});
    throw err;
  } finally {
    client.release();
  }
}

/** Quote an identifier. Names here come from pg_class, never from a request. */
function ident(name) {
  return `"${String(name).replaceAll('"', '""')}"`;
}

// `npm run lifecycle`: one run from the command line, then exit.
if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const { closePool } = await import('../db/pool.js');
  try {
    console.log(JSON.stringify(await runLifecycle(), null, 2));
  } finally {
    await closePool();
  }
}

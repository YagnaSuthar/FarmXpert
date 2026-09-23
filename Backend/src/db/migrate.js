/**
 * Migration runner.
 *
 *   npm run migrate          apply pending migrations
 *   npm run migrate:status   list applied and pending
 *
 * Plain `.sql` files in ./migrations, applied in name order, each in its own
 * transaction. Three rules make it safe to run on every deploy:
 *
 *   * An advisory lock: two instances starting at once cannot both migrate.
 *   * A checksum per applied file: editing a migration that has already run
 *     is refused, because the database would silently not match the file.
 *   * Idempotent: an applied migration is never run twice.
 *
 * Plain SQL rather than a DSL because this schema is PostGIS, pgvector,
 * partitions and triggers - a DSL would be a thin wrapper around raw SQL
 * everywhere that matters.
 */

import { createHash } from 'node:crypto';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { closePool, getPool } from './pool.js';

const MIGRATIONS_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), 'migrations');
// Arbitrary constant: any fixed 64-bit number works as long as it is shared.
const LOCK_ID = 7_261_442_901;

async function loadMigrations() {
  const files = (await readdir(MIGRATIONS_DIR)).filter((f) => /^\d{4}_.+\.sql$/.test(f)).sort();
  return Promise.all(files.map(async (name) => {
    const sql = await readFile(path.join(MIGRATIONS_DIR, name), 'utf8');
    return { name, sql, checksum: createHash('sha256').update(sql).digest('hex') };
  }));
}

export async function migrate({ log = console.log } = {}) {
  const client = await getPool().connect();
  try {
    await client.query('SELECT pg_advisory_lock($1)', [LOCK_ID]);
    await client.query(`
      CREATE TABLE IF NOT EXISTS schema_migrations (
        name       text PRIMARY KEY,
        checksum   text NOT NULL,
        applied_at timestamptz NOT NULL DEFAULT now()
      )`);

    const applied = new Map(
      (await client.query('SELECT name, checksum FROM schema_migrations')).rows
        .map((row) => [row.name, row.checksum]),
    );

    let ran = 0;
    for (const migration of await loadMigrations()) {
      const previous = applied.get(migration.name);
      if (previous) {
        if (previous !== migration.checksum) {
          throw new Error(
            `Migration ${migration.name} was edited after it was applied. ` +
            'Write a new migration instead of changing an old one.');
        }
        continue;
      }
      log(`applying ${migration.name}`);
      await client.query('BEGIN');
      try {
        await client.query(migration.sql);
        await client.query('INSERT INTO schema_migrations (name, checksum) VALUES ($1, $2)',
          [migration.name, migration.checksum]);
        await client.query('COMMIT');
      } catch (err) {
        await client.query('ROLLBACK').catch(() => {});
        err.message = `${migration.name}: ${err.message}`;
        throw err;
      }
      ran += 1;
    }
    log(ran ? `applied ${ran} migration(s)` : 'database is up to date');
    return ran;
  } finally {
    await client.query('SELECT pg_advisory_unlock($1)', [LOCK_ID]).catch(() => {});
    client.release();
  }
}

export async function status() {
  const migrations = await loadMigrations();
  const { rows } = await getPool().query(
    `SELECT name, applied_at FROM schema_migrations ORDER BY name`,
  ).catch(() => ({ rows: [] }));
  const applied = new Map(rows.map((r) => [r.name, r.applied_at]));
  return migrations.map((m) => ({ name: m.name, appliedAt: applied.get(m.name) ?? null }));
}

export { loadMigrations };

// Run directly: `node src/db/migrate.js [--status]`
if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const run = process.argv.includes('--status')
    ? status().then((list) => list.forEach((m) =>
      console.log(`${m.appliedAt ? 'applied ' : 'pending '} ${m.name}`)))
    : migrate();
  run.then(() => closePool()).catch(async (err) => {
    console.error(err.message);
    await closePool();
    process.exit(1);
  });
}

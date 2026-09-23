import assert from 'node:assert/strict';
import { test } from 'node:test';

import { loadMigrations } from '../src/db/migrate.js';
import { PARTITIONED } from '../src/jobs/storageLifecycle.js';

const migrations = await loadMigrations();
const allSql = migrations.map((m) => m.sql).join('\n');
// One entry per CREATE TABLE statement (comments stripped), so no pattern can
// run on into the next table.
const tables = allSql
  .replace(/--[^\n]*/g, '')
  .split(';')
  .map((stmt) => /CREATE TABLE (\w+) \(([\s\S]*?)\)\s*(?:PARTITION BY RANGE \((\w+)\))?\s*$/.exec(stmt.trim()))
  .filter(Boolean)
  .map((m) => ({ name: m[1], body: m[2], partitionKey: m[3] }));

test('migrations are numbered 0001.. without gaps and have checksums', () => {
  migrations.forEach((m, i) => {
    assert.match(m.name, new RegExp(`^${String(i + 1).padStart(4, '0')}_[a-z0-9_]+\\.sql$`));
    assert.match(m.checksum, /^[0-9a-f]{64}$/);
  });
  assert.ok(migrations.length >= 8);
  assert.ok(tables.length >= 20, `parsed ${tables.length} tables`);
});

test('every partitioned table gets its rolling partitions and a lifecycle policy', () => {
  const declared = tables.filter((t) => t.partitionKey).map((t) => t.name);
  assert.deepEqual(declared.sort(), [...PARTITIONED].sort());
  for (const table of PARTITIONED) {
    assert.ok(allSql.includes(`farmxpert_rolling_partitions('${table}')`), `${table} partitions`);
    assert.ok(allSql.includes(`('${table}',`), `${table} retention policy`);
  }
});

test('partitioned primary keys include the partition key', () => {
  for (const t of tables.filter((x) => x.partitionKey)) {
    const pk = /PRIMARY KEY \(([^)]*)\)/.exec(t.body);
    assert.ok(pk && pk[1].split(',').map((c) => c.trim()).includes(t.partitionKey), `${t.name} primary key`);
  }
});

test('money is NUMERIC, never float', () => {
  let seen = 0;
  for (const t of tables) {
    // Column definitions only: a line directly in the table body.
    for (const m of t.body.matchAll(/^ {4}(\w*price\w*|revenue|cost) +(\w+)/gm)) {
      seen += 1;
      assert.equal(m[2].toLowerCase(), 'numeric', `${t.name}.${m[1]} is ${m[2]}`);
    }
  }
  assert.ok(seen >= 7, `found ${seen} money columns`);
});

import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { test } from 'node:test';

import * as store from '../src/jobs/archiveStore.js';
import { retirePlan } from '../src/jobs/storageLifecycle.js';

test('only months wholly older than the hot window retire, oldest first', () => {
  const names = ['messages_2026_09', 'messages_2025_08', 'messages_2025_09', 'messages_2025_10',
    'messages_default', 'agent_outputs_2020_01'];
  const plan = retirePlan(names, 'messages', 12, new Date('2026-09-23T12:00:00Z'));
  // Cutoff is 2025-09-01: August 2025 ends on it, September 2025 does not.
  assert.deepEqual(plan.map((p) => p.name), ['messages_2025_08']);
  assert.equal(plan[0].start.toISOString(), '2025-08-01T00:00:00.000Z');
  assert.equal(plan[0].end.toISOString(), '2025-09-01T00:00:00.000Z');
});

test('the default partition and other tables are never retired', () => {
  const plan = retirePlan(['soil_data_default', 'soil_data_extra_2020_01'], 'soil_data', 1, new Date());
  assert.deepEqual(plan, []);
});

test('archive file round-trip: written rows are read back and counted', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'farmxpert-archive-'));
  try {
    const uri = pathToFileURL(dir).href;
    const writer = await store.open(uri, 'messages', 'messages_2025_08');
    for (let i = 0; i < 12_345; i += 1) await writer.write({ i, text: `line ${i}\nwith newline` });
    assert.equal(await writer.close(), 12_345);
    const { uri: fileUri, bytes } = await store.finalize(writer);
    assert.ok(fileUri.endsWith('messages_2025_08.ndjson.gz'));
    assert.ok(bytes > 0);
    const check = await store.verify(writer.finalPath);
    assert.equal(check.rows, 12_345, 'escaped newlines inside values do not split rows');
    assert.match(check.sha256, /^[0-9a-f]{64}$/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('only file:// archives are accepted', () => {
  assert.throws(() => store.rootDir('s3://bucket/x'), /Unsupported/);
});

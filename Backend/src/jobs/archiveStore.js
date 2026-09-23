/**
 * Where cold partitions go: gzip-compressed NDJSON, one file per partition.
 *
 * `file://` covers a local disk or any mounted volume (a network share, or a
 * bucket mounted with s3fs/gcsfuse). An object-store backend needs only these
 * three functions: `open`, `finalize`, `verify`.
 *
 * Nothing is trusted until it is read back: `verify` decompresses the whole
 * file and counts its lines and checksum before a partition may be dropped.
 */

import { createHash } from 'node:crypto';
import { createReadStream, createWriteStream } from 'node:fs';
import { mkdir, rename, rm, stat } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { pipeline } from 'node:stream/promises';
import { fileURLToPath } from 'node:url';
import { createGunzip, createGzip } from 'node:zlib';

export function rootDir(archiveUri) {
  if (!archiveUri.startsWith('file://')) {
    throw new Error(`Unsupported ARCHIVE_URI scheme: ${archiveUri} (only file:// is implemented)`);
  }
  // file://./archive is relative to the working directory.
  const rest = archiveUri.slice('file://'.length);
  return rest.startsWith('/') || /^[A-Za-z]:/.test(rest) ? fileURLToPath(archiveUri) : resolve(rest);
}

/**
 * Open `<root>/<table>/<name>.ndjson.gz.part` for writing. Returns a writer
 * with `write(obj)` (respecting backpressure) and `close()`.
 */
export async function open(archiveUri, table, name) {
  const finalPath = join(rootDir(archiveUri), table, `${name}.ndjson.gz`);
  const partPath = `${finalPath}.part`;
  await mkdir(dirname(finalPath), { recursive: true });

  const gzip = createGzip({ level: 6 });
  const file = createWriteStream(partPath);
  const done = pipeline(gzip, file);
  let rows = 0;

  return {
    finalPath,
    partPath,
    async write(obj) {
      rows += 1;
      if (!gzip.write(`${JSON.stringify(obj)}\n`)) {
        await new Promise((r) => gzip.once('drain', r));
      }
    },
    async close() {
      gzip.end();
      await done;
      return rows;
    },
  };
}

/** Move the finished file into place; only a complete file has the final name. */
export async function finalize(writer) {
  await rename(writer.partPath, writer.finalPath);
  const { size } = await stat(writer.finalPath);
  return { uri: `file://${writer.finalPath.replaceAll('\\', '/')}`, bytes: size };
}

/** Read the file back in full. Returns { rows, sha256 } of the compressed bytes. */
export async function verify(path) {
  const hash = createHash('sha256');
  let rows = 0;
  let tail = '';
  const source = createReadStream(path);
  source.on('data', (chunk) => hash.update(chunk));
  const gunzip = createGunzip();
  gunzip.on('data', (chunk) => {
    const text = tail + chunk.toString('utf8');
    const lines = text.split('\n');
    tail = lines.pop();
    rows += lines.length;
  });
  await pipeline(source, gunzip);
  if (tail) rows += 1;
  return { rows, sha256: hash.digest('hex') };
}

export async function discard(writer) {
  await rm(writer.partPath, { force: true });
}

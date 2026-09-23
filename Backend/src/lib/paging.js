/**
 * Keyset pagination.
 *
 * `OFFSET 5000` reads and throws away 5000 rows; a keyset cursor
 * `(created_at, id) < ($1, $2)` seeks straight to the page through the index,
 * so page 100 costs the same as page 1. And a row inserted while a farmer
 * scrolls cannot shift the pages or show a message twice.
 *
 * Cursors are opaque base64url: clients pass them back, never parse them.
 */

export function encodeCursor(moment, id) {
  const iso = moment instanceof Date ? moment.toISOString() : String(moment);
  return Buffer.from(`${iso}|${id}`, 'utf8').toString('base64url');
}

/** Returns { at, id } or null. A tampered cursor restarts at the top. */
export function decodeCursor(cursor) {
  if (!cursor) return null;
  try {
    const [at, id] = Buffer.from(cursor, 'base64url').toString('utf8').split('|');
    const moment = new Date(at);
    if (Number.isNaN(moment.getTime()) || !/^[0-9a-f-]{36}$/i.test(id || '')) return null;
    return { at: moment, id };
  } catch {
    return null;
  }
}

/**
 * Turn `limit + 1` rows into a page. Fetching one extra row is how we know
 * whether there is a next page without a separate COUNT query.
 */
export function toPage(rows, limit, keyOf) {
  const hasMore = rows.length > limit;
  const items = hasMore ? rows.slice(0, limit) : rows;
  const last = items[items.length - 1];
  const next = hasMore && last ? encodeCursor(...keyOf(last)) : null;
  return { items, nextCursor: next };
}

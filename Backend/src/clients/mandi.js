/**
 * data.gov.in AGMARKNET daily mandi prices.
 *
 * Fixes two bugs from the old Python ingester: the resource id was the
 * literal placeholder "YOUR_RESOURCE_ID", so ingestion never fetched
 * anything; and a missing price became 0.0, which dragged every average
 * toward zero. A missing price is null here and stays null in the database.
 */

import { config } from '../config/env.js';

const BASE = 'https://api.data.gov.in/resource';

export function mandiConfigured() {
  return Boolean(config.mandi.apiKey && config.mandi.resourceId);
}

/** Records for one commodity, newest first, normalised for insertion. */
export async function fetchCommodity(commodity, { limit = 500, timeoutMs = 20000 } = {}) {
  const url = new URL(`${BASE}/${encodeURIComponent(config.mandi.resourceId)}`);
  url.searchParams.set('api-key', config.mandi.apiKey);
  url.searchParams.set('format', 'json');
  url.searchParams.set('limit', String(limit));
  url.searchParams.set('filters[commodity]', commodity);

  const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
  if (!response.ok) throw new Error(`data.gov.in answered ${response.status}`);
  const body = await response.json();
  return (body.records || []).map(normaliseRecord).filter(Boolean);
}

export function normaliseRecord(raw) {
  const commodity = text(raw.commodity, 100);
  const market = text(raw.market, 100);
  const arrivalDate = parseDate(raw.arrival_date);
  if (!commodity || !market || !arrivalDate) return null;

  let min = price(raw.min_price);
  let max = price(raw.max_price);
  let modal = price(raw.modal_price);
  // Rows that break the table's ordering checks are feed errors; keep the
  // modal price (the one the forecast uses) only if it stays consistent.
  if (min !== null && max !== null && max < min) [min, max] = [null, null];
  if (modal !== null && min !== null && max !== null && (modal < min || modal > max)) modal = null;

  return {
    commodity,
    market,
    state: text(raw.state, 80),
    district: text(raw.district, 80),
    arrivalDate,
    minPrice: min,
    maxPrice: max,
    modalPrice: modal,
    variety: text(raw.variety, 100) || '',
    grade: text(raw.grade, 50) || '',
  };
}

function text(value, max) {
  if (value === undefined || value === null) return null;
  const out = String(value).trim();
  return out ? out.slice(0, max) : null;
}

/** A positive price, or null. Never 0 for "missing". */
function price(value) {
  if (value === undefined || value === null || value === '' || value === 'NR') return null;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 && n < 10_000_000 ? Math.round(n * 100) / 100 : null;
}

/** AGMARKNET sends DD/MM/YYYY; accept ISO too. Returns YYYY-MM-DD or null. */
export function parseDate(value) {
  if (!value) return null;
  const s = String(value).trim();
  let m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(s);
  const iso = m ? `${m[3]}-${m[2]}-${m[1]}` : (/^\d{4}-\d{2}-\d{2}/.exec(s) || [])[0];
  if (!iso) return null;
  m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCDate() === +m[3] && d.getUTCMonth() === +m[2] - 1 ? iso : null;
}

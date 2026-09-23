import { Router } from 'express';

import { fetchCommodity } from '../clients/mandi.js';
import { query } from '../db/pool.js';
import { logger } from '../lib/logger.js';
import { idParam, validate } from '../lib/validate.js';
import { authenticate, requireFarm } from './auth/middleware.js';

export const marketRoutes = Router();

const text = (max) => ({ type: 'string', minLength: 1, maxLength: max });

// Exact, case-insensitive match served by the lower(commodity) index. The old
// ILIKE '%x%' could not use an index and matched "Rice" inside "Price".
marketRoutes.get(
  '/market/prices',
  validate({
    query: {
      type: 'object',
      properties: {
        commodity: text(100),
        state: text(80),
        district: text(80),
        market: text(100),
        days: { type: 'integer', minimum: 1, maximum: 365, default: 30 },
        limit: { type: 'integer', minimum: 1, maximum: 500, default: 100 },
      },
      required: ['commodity'],
    },
  }),
  async (req, res) => {
    const q = req.query;
    const { rows } = await query(
      `SELECT commodity, market, state, district, arrival_date, variety, grade,
              min_price::float8 AS min_price, max_price::float8 AS max_price,
              modal_price::float8 AS modal_price
         FROM mandi_price_data
        WHERE lower(commodity) = lower($1)
          AND arrival_date >= CURRENT_DATE - $2::int
          AND ($3::text IS NULL OR lower(state) = lower($3))
          AND ($4::text IS NULL OR lower(district) = lower($4))
          AND ($5::text IS NULL OR lower(market) = lower($5))
        ORDER BY arrival_date DESC, modal_price DESC NULLS LAST
        LIMIT $6`,
      [q.commodity, q.days, q.state ?? null, q.district ?? null, q.market ?? null, q.limit],
    );
    const modal = rows.map((r) => r.modal_price).filter((v) => v !== null);
    res.json({
      items: rows,
      summary: modal.length
        ? {
          observations: modal.length,
          modal_avg: Math.round((modal.reduce((a, b) => a + b, 0) / modal.length) * 100) / 100,
          modal_min: Math.min(...modal),
          modal_max: Math.max(...modal),
        }
        : null,
    });
  },
);

marketRoutes.get(
  '/farms/:id/market-recommendations',
  authenticate,
  validate({ params: idParam }),
  requireFarm(),
  async (req, res) => {
    const { rows } = await query(
      `SELECT id, commodity, location, best_market, best_price::float8 AS best_price, forecast_trend,
              predicted_price::float8 AS predicted_price, recommendation, confidence, reasoning,
              agent_version, created_at
         FROM market_recommendations WHERE farm_id = $1 ORDER BY created_at DESC LIMIT 20`,
      [req.params.id],
    );
    res.json({ items: rows });
  },
);

/**
 * Fetch and upsert today's prices for each configured commodity. A re-fetch
 * corrects a price in place (the natural key) instead of adding a duplicate.
 * Returns per-commodity counts; one failing commodity does not stop the rest.
 */
export async function ingestMandiPrices(commodities) {
  const report = {};
  for (const commodity of commodities) {
    try {
      const records = await fetchCommodity(commodity);
      report[commodity] = records.length ? await upsertPrices(records) : 0;
    } catch (err) {
      logger.warn({ err: err.message, commodity }, 'Mandi fetch failed');
      report[commodity] = 'failed';
    }
  }
  return report;
}

async function upsertPrices(records) {
  // One statement for the whole batch via unnest: a round trip per row would
  // turn a 500-row fetch into 500 network waits.
  const cols = ['commodity', 'market', 'state', 'district', 'arrivalDate', 'minPrice', 'maxPrice',
    'modalPrice', 'variety', 'grade'];
  // Collapse duplicates inside one response, which ON CONFLICT cannot do.
  const unique = new Map();
  for (const r of records) unique.set([r.commodity, r.market, r.arrivalDate, r.variety, r.grade].join('|'), r);
  const batch = [...unique.values()];
  const arrays = cols.map((c) => batch.map((r) => r[c]));
  const { rowCount } = await query(
    `INSERT INTO mandi_price_data (commodity, market, state, district, arrival_date,
                                   min_price, max_price, modal_price, variety, grade)
     SELECT * FROM unnest($1::text[], $2::text[], $3::text[], $4::text[], $5::date[],
                          $6::numeric[], $7::numeric[], $8::numeric[], $9::text[], $10::text[])
     ON CONFLICT ON CONSTRAINT uq_mandi_price_data_observation DO UPDATE SET
         min_price = EXCLUDED.min_price, max_price = EXCLUDED.max_price,
         modal_price = EXCLUDED.modal_price, state = EXCLUDED.state, district = EXCLUDED.district
       WHERE (mandi_price_data.min_price, mandi_price_data.max_price, mandi_price_data.modal_price)
             IS DISTINCT FROM (EXCLUDED.min_price, EXCLUDED.max_price, EXCLUDED.modal_price)`,
    arrays,
  );
  return rowCount;
}

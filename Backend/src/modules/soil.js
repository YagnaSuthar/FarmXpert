/**
 * Soil readings and the Blynk devices that produce them.
 */

import { Router } from 'express';

import { readPins } from '../clients/blynk.js';
import { one, query, transaction } from '../db/pool.js';
import { HttpError, conflict, notFound } from '../lib/errors.js';
import { decodeCursor, toPage } from '../lib/paging.js';
import { idParam, pageQuery, validate } from '../lib/validate.js';
import { authenticate, requireFarm, requireOwned } from './auth/middleware.js';

export const soilRoutes = Router();

export const READING_FIELDS = [
  'soil_moisture', 'soil_temperature', 'soil_ph', 'electrical_conductivity', 'nitrogen',
  'phosphorus', 'potassium', 'air_temperature', 'air_humidity', 'soil_type', 'crop_type',
  'rainfall', 'irrigation_type', 'irrigation_amount', 'fertilizer_type', 'fertilizer_amount',
];
const READING_COLUMNS = `id, farm_id, field_id, recorded_at, source, device_id, ${READING_FIELDS.join(', ')}`;

const range = (minimum, maximum) => ({ type: 'number', minimum, maximum });
const readingBody = {
  type: 'object',
  properties: {
    field_id: { type: 'string', format: 'uuid' },
    recorded_at: { type: 'string', format: 'date-time' },
    source: { enum: ['sensor', 'lab', 'manual', 'estimated'], default: 'manual' },
    device_id: { type: 'string', maxLength: 64 },
    soil_moisture: range(0, 100),
    soil_temperature: range(-20, 80),
    soil_ph: range(0, 14),
    electrical_conductivity: range(0, 30),
    nitrogen: range(0, 2000),
    phosphorus: range(0, 2000),
    potassium: range(0, 5000),
    air_temperature: range(-40, 60),
    air_humidity: range(0, 100),
    soil_type: { type: 'string', maxLength: 50 },
    crop_type: { type: 'string', maxLength: 50 },
    rainfall: range(0, 2000),
    irrigation_type: { type: 'string', maxLength: 50 },
    irrigation_amount: range(0, 100000),
    fertilizer_type: { type: 'string', maxLength: 100 },
    fertilizer_amount: range(0, 100000),
  },
  // A reading with no measurement in it is not a reading.
  anyOf: ['soil_moisture', 'soil_ph', 'nitrogen', 'soil_temperature', 'electrical_conductivity']
    .map((f) => ({ required: [f] })),
};

/** Insert one reading. Returns the row, or null when it is a retried duplicate. */
export async function insertReading(farmId, reading, db = { query }) {
  const values = READING_FIELDS.map((f) => reading[f] ?? null);
  const { rows } = await db.query(
    `INSERT INTO soil_data (farm_id, field_id, recorded_at, source, device_id, ${READING_FIELDS.join(', ')})
     VALUES ($1, $2, COALESCE($3::timestamptz, now()), $4, $5,
             ${READING_FIELDS.map((_, i) => `$${i + 6}`).join(', ')})
     ON CONFLICT DO NOTHING
     RETURNING ${READING_COLUMNS}`,
    [farmId, reading.field_id ?? null, reading.recorded_at ?? null, reading.source ?? 'manual',
      reading.device_id ?? null, ...values],
  );
  return rows[0] ?? null;
}

/** The newest reading for a farm, or one field: what the chat path sends to the AI. */
export async function latestReading(farmId, fieldId = null) {
  return one(
    `SELECT ${READING_COLUMNS} FROM soil_data
      WHERE farm_id = $1 AND ($2::uuid IS NULL OR field_id = $2)
      ORDER BY recorded_at DESC LIMIT 1`,
    [farmId, fieldId],
  );
}

async function farmExists(id) {
  const farm = await one('SELECT id FROM farms WHERE id = $1 AND deleted_at IS NULL', [id]);
  if (!farm) throw notFound('Farm');
  return farm;
}

soilRoutes.post('/farms/:id/soil', authenticate, validate({ params: idParam, body: readingBody }), requireFarm(), async (req, res) => {
  await farmExists(req.params.id);
  const row = await insertReading(req.params.id, req.body);
  // A retry of an already-stored reading is success, not an error.
  res.status(row ? 201 : 200).json(row ?? { duplicate: true });
});

soilRoutes.get(
  '/farms/:id/soil/latest',
  authenticate,
  validate({ params: idParam, query: { type: 'object', properties: { field_id: { type: 'string', format: 'uuid' } } } }),
  requireFarm(),
  async (req, res) => {
    const row = await latestReading(req.params.id, req.query.field_id ?? null);
    if (!row) throw notFound('Soil reading');
    res.json(row);
  },
);

soilRoutes.get(
  '/farms/:id/soil',
  authenticate,
  validate({
    params: idParam,
    query: {
      type: 'object',
      properties: { ...pageQuery, since: { type: 'string', format: 'date-time' } },
    },
  }),
  requireFarm(),
  async (req, res) => {
    const { limit, cursor, since } = req.query;
    const after = decodeCursor(cursor);
    const { rows } = await query(
      `SELECT ${READING_COLUMNS} FROM soil_data
        WHERE farm_id = $1
          AND ($2::timestamptz IS NULL OR recorded_at >= $2)
          AND ($3::timestamptz IS NULL OR (recorded_at, id) < ($3, $4::uuid))
        ORDER BY recorded_at DESC, id DESC LIMIT $5`,
      [req.params.id, since ?? null, after?.at ?? null, after?.id ?? null, limit + 1],
    );
    res.json(toPage(rows, limit, (r) => [r.recorded_at, r.id]));
  },
);

// ── devices ─────────────────────────────────────────────────────────────────

// Never returns the token itself: only its last four characters.
const DEVICE_COLUMNS = `id, farm_id, label, is_active, revoked_at, last_seen_at, created_at,
  right(token, 4) AS token_hint`;

soilRoutes.post(
  '/farms/:id/devices',
  authenticate,
  validate({
    params: idParam,
    body: {
      type: 'object',
      properties: {
        token: { type: 'string', minLength: 8, maxLength: 100 },
        label: { type: 'string', maxLength: 80 },
      },
      required: ['token'],
    },
  }),
  requireFarm(),
  async (req, res) => {
    await farmExists(req.params.id);
    // Rotate: revoke the active token and register the new one atomically,
    // so the one-active-token index never sees two.
    const device = await transaction(async (client) => {
      await client.query(
        'UPDATE blynk_tokens SET is_active = false, revoked_at = now() WHERE farm_id = $1 AND is_active',
        [req.params.id],
      );
      const { rows } = await client.query(
        `INSERT INTO blynk_tokens (farm_id, token, label) VALUES ($1, $2, $3) RETURNING ${DEVICE_COLUMNS}`,
        [req.params.id, req.body.token, req.body.label ?? null],
      );
      return rows[0];
    }).catch((err) => {
      if (err.code === '23505') throw conflict('That device token is already registered.');
      throw err;
    });
    res.status(201).json(device);
  },
);

soilRoutes.get('/farms/:id/devices', authenticate, validate({ params: idParam }), requireFarm(), async (req, res) => {
  const { rows } = await query(
    `SELECT ${DEVICE_COLUMNS} FROM blynk_tokens WHERE farm_id = $1 ORDER BY created_at DESC`,
    [req.params.id],
  );
  res.json({ items: rows });
});

soilRoutes.delete('/devices/:id', authenticate, validate({ params: idParam }), requireOwned('blynk_tokens'), async (req, res) => {
  const { rowCount } = await query(
    'UPDATE blynk_tokens SET is_active = false, revoked_at = now() WHERE id = $1 AND is_active',
    [req.params.id],
  );
  if (!rowCount) throw notFound('Active device');
  res.status(204).end();
});

/** Pull the current reading from the farm's active device and store it. */
export async function syncDevice(farmId) {
  const device = await one(
    'SELECT id, token FROM blynk_tokens WHERE farm_id = $1 AND is_active',
    [farmId],
  );
  if (!device) throw notFound('Active device for this farm');

  let pins;
  try {
    pins = await readPins(device.token);
  } catch (err) {
    if (err.code === 'invalid_token') {
      throw new HttpError(422, 'invalid_device_token', 'Blynk rejected this farm\'s device token.');
    }
    throw new HttpError(502, 'device_unreachable', 'The device service could not be reached.');
  }
  if (!Object.keys(pins.reading).length) {
    throw new HttpError(422, 'no_measurements', 'The device reported no usable measurements.');
  }
  // Truncated to the minute: a double-tap on "sync" stores one reading.
  const recordedAt = new Date(Math.floor(Date.now() / 60000) * 60000).toISOString();
  const row = await insertReading(farmId, {
    ...pins.reading, source: 'sensor', device_id: `blynk:${device.id}`, recorded_at: recordedAt,
  });
  await query('UPDATE blynk_tokens SET last_seen_at = now() WHERE id = $1', [device.id]);
  return { reading: row, dropped_channels: pins.dropped, duplicate: !row };
}

soilRoutes.post('/farms/:id/devices/sync', authenticate, validate({ params: idParam }), requireFarm(), async (req, res) => {
  await farmExists(req.params.id);
  res.json(await syncDevice(req.params.id));
});

/**
 * Farms and fields.
 *
 * Clients speak latitude/longitude and acres or hectares; the database stores
 * a PostGIS point and hectares. Conversion happens here, once.
 */

import { Router } from 'express';

import { one, query } from '../db/pool.js';
import { badRequest, notFound } from '../lib/errors.js';
import { acresToHectares, hectaresToAcres, pointWkt, round } from '../lib/units.js';
import { idParam, latitude, longitude, uuid, validate } from '../lib/validate.js';
import { STAFF, authenticate, requireFarm, requireOwned } from './auth/middleware.js';

export const farmRoutes = Router();

const FARM_COLUMNS = `id, user_id, name, latitude, longitude, area_hectares, address, state,
  district, timezone, water_source, resources, created_at, updated_at`;
const FIELD_COLUMNS = `id, farm_id, name, area_hectares, soil_type, irrigation_method, crop_id,
  crop_name, growth_stage, sown_on, expected_harvest_on, ST_AsGeoJSON(boundary)::json AS boundary,
  created_at, updated_at`;

function presentArea(row) {
  if (!row) return row;
  const hectares = row.area_hectares === null ? null : Number(row.area_hectares);
    // Two decimals: hectares are stored to 3, so 5 acres comes back as 5, not 4.999.
  return { ...row, area_hectares: hectares, area_acres: hectares === null ? null : round(hectaresToAcres(hectares), 2) };
}

/** Hectares from whichever unit the client sent; acres win only when hectares is absent. */
function areaFrom(body) {
  if (body.area_hectares !== undefined) return body.area_hectares;
  if (body.area_acres !== undefined) return round(acresToHectares(body.area_acres), 3);
  return undefined;
}

const area = { type: 'number', exclusiveMinimum: 0, maximum: 100000 };
const farmProps = {
  name: { type: 'string', maxLength: 120 },
  latitude,
  longitude,
  area_hectares: area,
  area_acres: area,
  address: { type: 'string', maxLength: 255 },
  state: { type: 'string', maxLength: 80 },
  district: { type: 'string', maxLength: 80 },
  timezone: { type: 'string', maxLength: 64 },
  water_source: { enum: ['borewell', 'canal', 'well', 'river', 'pond', 'rainfed', 'tanker', 'other'] },
  // What the task scheduler plans within, and whether irrigation is possible.
  resources: {
    type: 'object',
    properties: {
      irrigation_available: { type: 'boolean' },
      labor_units_available: { type: 'integer', minimum: 0, maximum: 500 },
      water_available_liters: { type: 'number', minimum: 0, maximum: 1e9 },
      equipment_available: { type: 'array', items: { type: 'string', maxLength: 40 }, maxItems: 30 },
      budget_available: { type: 'number', minimum: 0, maximum: 1e9 },
      working_hours_start: { type: 'string', pattern: '^([01][0-9]|2[0-3]):[0-5][0-9]$' },
      working_hours_end: { type: 'string', pattern: '^([01][0-9]|2[0-3]):[0-5][0-9]$' },
    },
  },
};

farmRoutes.post(
  '/farms',
  authenticate,
  validate({
    body: {
      type: 'object',
      properties: farmProps,
      dependentRequired: { latitude: ['longitude'], longitude: ['latitude'] },
    },
  }),
  async (req, res) => {
    res.status(201).json(presentArea(await createFarm({ query }, req.user.id, req.body)));
  },
);

/** Insert a farm for its owner. Shared with onboarding (inside its transaction). */
export async function createFarm(db, userId, b) {
  const { rows } = await db.query(
    `INSERT INTO farms (user_id, name, location, area_hectares, address, state, district, timezone,
                        water_source, resources)
     VALUES ($1, $2, $3::geography, $4, $5, $6, $7, COALESCE($8, 'Asia/Kolkata'), $9, COALESCE($10, '{}'::jsonb))
     RETURNING ${FARM_COLUMNS}`,
    [userId, b.name ?? null, b.latitude === undefined ? null : pointWkt(b.latitude, b.longitude),
      areaFrom(b) ?? null, b.address ?? null, b.state ?? null, b.district ?? null, b.timezone ?? null,
      b.water_source ?? null, b.resources ? JSON.stringify(b.resources) : null],
  );
  return rows[0];
}

farmRoutes.get(
  '/farms',
  authenticate,
  validate({ query: { type: 'object', properties: { user_id: uuid } } }),
  async (req, res) => {
    const owner = STAFF.has(req.user.role) && req.query.user_id ? req.query.user_id : req.user.id;
    const { rows } = await query(
      `SELECT ${FARM_COLUMNS} FROM farms WHERE user_id = $1 AND deleted_at IS NULL
        ORDER BY created_at DESC LIMIT 200`,
      [owner],
    );
    res.json({ items: rows.map(presentArea) });
  },
);

farmRoutes.get('/farms/:id', authenticate, validate({ params: idParam }), requireFarm(), async (req, res) => {
  const farm = await one(`SELECT ${FARM_COLUMNS} FROM farms WHERE id = $1 AND deleted_at IS NULL`, [req.params.id]);
  if (!farm) throw notFound('Farm');
  res.json(presentArea(farm));
});

farmRoutes.patch(
  '/farms/:id',
  authenticate,
  validate({
    params: idParam,
    body: {
      type: 'object',
      properties: farmProps,
      minProperties: 1,
      dependentRequired: { latitude: ['longitude'], longitude: ['latitude'] },
    },
  }),
  requireFarm(),
  async (req, res) => {
    const b = req.body;
    const farm = await one(
      `UPDATE farms SET
          name = COALESCE($2, name),
          location = COALESCE($3::geography, location),
          area_hectares = COALESCE($4, area_hectares),
          address = COALESCE($5, address),
          state = COALESCE($6, state),
          district = COALESCE($7, district),
          timezone = COALESCE($8, timezone),
          water_source = COALESCE($9, water_source),
          resources = CASE WHEN $10::jsonb IS NULL THEN resources ELSE resources || $10::jsonb END
        WHERE id = $1 AND deleted_at IS NULL RETURNING ${FARM_COLUMNS}`,
      [req.params.id, b.name ?? null, b.latitude === undefined ? null : pointWkt(b.latitude, b.longitude),
        areaFrom(b) ?? null, b.address ?? null, b.state ?? null, b.district ?? null, b.timezone ?? null,
        b.water_source ?? null, b.resources ? JSON.stringify(b.resources) : null],
    );
    if (!farm) throw notFound('Farm');
    res.json(presentArea(farm));
  },
);

// Soft delete: readings and history stay for the owner until the account is erased.
farmRoutes.delete('/farms/:id', authenticate, validate({ params: idParam }), requireFarm(), async (req, res) => {
  const { rowCount } = await query(
    'UPDATE farms SET deleted_at = now() WHERE id = $1 AND deleted_at IS NULL',
    [req.params.id],
  );
  if (!rowCount) throw notFound('Farm');
  res.status(204).end();
});

// ── fields ──────────────────────────────────────────────────────────────────

const date = { type: 'string', format: 'date' };
const fieldProps = {
  name: { type: 'string', minLength: 1, maxLength: 80 },
  area_hectares: area,
  area_acres: area,
  soil_type: { type: 'string', maxLength: 50 },
  irrigation_method: { type: 'string', maxLength: 30 },
  crop_name: { type: 'string', maxLength: 80 },
  growth_stage: { type: 'string', maxLength: 30 },
  sown_on: date,
  expected_harvest_on: date,
  // GeoJSON Polygon; PostGIS rejects an invalid ring with a clear error.
  boundary: {
    type: 'object',
    properties: { type: { const: 'Polygon' }, coordinates: { type: 'array', minItems: 1 } },
    required: ['type', 'coordinates'],
  },
};

const fieldValues = (b) => [
  b.name ?? null, areaFrom(b) ?? null, b.soil_type ?? null, b.irrigation_method ?? null,
  b.crop_name ?? null, b.growth_stage ?? null, b.sown_on ?? null, b.expected_harvest_on ?? null,
  b.boundary ? JSON.stringify(b.boundary) : null,
];

farmRoutes.post(
  '/farms/:id/fields',
  authenticate,
  validate({ params: idParam, body: { type: 'object', properties: fieldProps, required: ['name'] } }),
  requireFarm(),
  async (req, res) => {
    res.status(201).json(presentArea(await createField({ query }, req.params.id, req.body)));
  },
);

/** Insert a field. Shared with onboarding (inside its transaction). */
export async function createField(db, farmId, b) {
  if (b.sown_on && b.expected_harvest_on && b.expected_harvest_on < b.sown_on) {
    throw badRequest('expected_harvest_on is before sown_on.');
  }
  const { rows } = await db.query(
    `INSERT INTO fields (farm_id, name, area_hectares, soil_type, irrigation_method, crop_name,
                         growth_stage, sown_on, expected_harvest_on, boundary, crop_id)
     VALUES ($1, $2, $3, $4, $5, $6::text, $7, $8, $9,
             ST_SetSRID(ST_GeomFromGeoJSON($10), 4326)::geography,
             (SELECT id FROM crops WHERE slug = lower($6::text)))
     RETURNING ${FIELD_COLUMNS}`,
    [farmId, ...fieldValues(b)],
  );
  return presentArea(rows[0]);
}

export { presentArea };

farmRoutes.get('/farms/:id/fields', authenticate, validate({ params: idParam }), requireFarm(), async (req, res) => {
  const { rows } = await query(
    `SELECT ${FIELD_COLUMNS} FROM fields WHERE farm_id = $1 AND deleted_at IS NULL ORDER BY name`,
    [req.params.id],
  );
  res.json({ items: rows.map(presentArea) });
});

farmRoutes.patch(
  '/fields/:id',
  authenticate,
  validate({ params: idParam, body: { type: 'object', properties: fieldProps, minProperties: 1 } }),
  requireOwned('fields'),
  async (req, res) => {
    const b = req.body;
    if (b.sown_on && b.expected_harvest_on && b.expected_harvest_on < b.sown_on) {
      throw badRequest('expected_harvest_on is before sown_on.');
    }
    const field = await one(
      `UPDATE fields SET
          name = COALESCE($2, name),
          area_hectares = COALESCE($3, area_hectares),
          soil_type = COALESCE($4, soil_type),
          irrigation_method = COALESCE($5, irrigation_method),
          crop_name = COALESCE($6::text, crop_name),
          crop_id = CASE WHEN $6::text IS NULL THEN crop_id
                         ELSE (SELECT id FROM crops WHERE slug = lower($6::text)) END,
          growth_stage = COALESCE($7, growth_stage),
          sown_on = COALESCE($8, sown_on),
          expected_harvest_on = COALESCE($9, expected_harvest_on),
          boundary = COALESCE(ST_SetSRID(ST_GeomFromGeoJSON($10), 4326)::geography, boundary)
        WHERE id = $1 AND deleted_at IS NULL RETURNING ${FIELD_COLUMNS}`,
      [req.params.id, ...fieldValues(b)],
    );
    if (!field) throw notFound('Field');
    res.json(presentArea(field));
  },
);

farmRoutes.delete('/fields/:id', authenticate, validate({ params: idParam }), requireOwned('fields'), async (req, res) => {
  const { rowCount } = await query(
    'UPDATE fields SET deleted_at = now() WHERE id = $1 AND deleted_at IS NULL',
    [req.params.id],
  );
  if (!rowCount) throw notFound('Field');
  res.status(204).end();
});

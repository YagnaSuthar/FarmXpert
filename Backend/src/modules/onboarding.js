/**
 * Onboarding: everything the agents need, collected once.
 *
 *   GET  /onboarding          where the farmer is, plus the choices the form offers
 *   POST /onboarding/device   check a Blynk token and show what the probe reads
 *   POST /onboarding          profile + farm + field + soil + device, one transaction
 *
 * What each piece feeds:
 *   location, state, district   weather forecast, mandi prices, crop suitability
 *   area, soil type             irrigation depth and duration, fertiliser doses
 *   crop, stage, sowing date    irrigation schedule, task plan, crop calendar
 *   irrigation method, water    how the water can be applied, and whether at all
 *   soil reading (N P K pH ...) soil health, crop choice, fertiliser advice
 *   labour, equipment, budget   the task scheduler plans within them
 *   Blynk device                live readings instead of typed ones
 */

import { Router } from 'express';

import { readPins } from '../clients/blynk.js';
import { one, transaction } from '../db/pool.js';
import { HttpError, conflict } from '../lib/errors.js';
import { latitude, longitude, validate } from '../lib/validate.js';
import { authenticate } from './auth/middleware.js';
import { createFarm, createField, presentArea } from './farms.js';
import { insertReading } from './soil.js';

export const onboardingRoutes = Router();

// The vocabularies the agents understand (AI_Backend irrigation/soil configs).
export const OPTIONS = Object.freeze({
  soil_types: ['alluvial', 'black_cotton', 'red_laterite', 'loamy', 'sandy_loam', 'sandy', 'clay_loam',
    'clay', 'silt', 'peaty'],
  irrigation_methods: ['drip', 'sprinkler', 'furrow', 'flood', 'basin', 'border', 'center_pivot', 'rainfed'],
  growth_stages: ['germination', 'seedling', 'vegetative', 'flowering', 'fruiting', 'maturation',
    'harvest_ready'],
  water_sources: ['borewell', 'canal', 'well', 'river', 'pond', 'rainfed', 'tanker', 'other'],
  equipment: ['tractor', 'power_tiller', 'sprayer', 'drone_sprayer', 'seed_drill', 'harvester', 'pump',
    'drip_system', 'sprinkler_set'],
  crops: ['wheat', 'rice', 'cotton', 'maize', 'soybean', 'groundnut', 'sugarcane', 'mustard', 'chickpea',
    'pigeonpea', 'green_gram', 'black_gram', 'bajra', 'jowar', 'ragi', 'potato', 'onion', 'tomato',
    'chilli', 'banana', 'mango', 'turmeric', 'cumin', 'castor', 'sesame'],
});

onboardingRoutes.get('/onboarding', authenticate, async (req, res) => {
  const farm = await one(
    `SELECT id, name FROM farms WHERE user_id = $1 AND deleted_at IS NULL ORDER BY created_at LIMIT 1`,
    [req.user.id],
  );
  res.json({ onboarded: Boolean(req.user.onboarded_at), farm, options: OPTIONS });
});

const token = { type: 'string', minLength: 8, maxLength: 100, pattern: '^[A-Za-z0-9_-]+$' };

// Lets the farmer see their probe is connected before finishing the form.
onboardingRoutes.post(
  '/onboarding/device',
  authenticate,
  validate({ body: { type: 'object', properties: { token }, required: ['token'] } }),
  async (req, res) => {
    try {
      const { reading, dropped } = await readPins(req.body.token);
      res.json({ ok: Object.keys(reading).length > 0, reading, dropped_channels: dropped });
    } catch (err) {
      if (err.code === 'invalid_token') {
        throw new HttpError(422, 'invalid_device_token', 'Blynk did not accept this token. Please check it.');
      }
      throw new HttpError(502, 'device_unreachable', 'Could not reach the device service. You can add it later.');
    }
  },
);

const num = (minimum, maximum) => ({ type: 'number', minimum, maximum });
const date = { type: 'string', format: 'date' };
const text = (max) => ({ type: 'string', minLength: 1, maxLength: max });

const onboardingBody = {
  type: 'object',
  properties: {
    profile: {
      type: 'object',
      properties: {
        name: { type: 'string', minLength: 2, maxLength: 120 },
        phone: { type: 'string', pattern: '^[0-9+][0-9]{7,14}$' },
        language: text(12),
      },
    },
    farm: {
      type: 'object',
      properties: {
        name: text(120),
        latitude,
        longitude,
        area_acres: { type: 'number', exclusiveMinimum: 0, maximum: 100000 },
        address: text(255),
        state: text(80),
        district: text(80),
        water_source: { enum: OPTIONS.water_sources },
        resources: {
          type: 'object',
          properties: {
            irrigation_available: { type: 'boolean' },
            labor_units_available: { type: 'integer', minimum: 0, maximum: 500 },
            water_available_liters: num(0, 1e9),
            equipment_available: { type: 'array', items: { enum: OPTIONS.equipment }, maxItems: 20 },
            budget_available: num(0, 1e9),
            working_hours_start: { type: 'string', pattern: '^([01][0-9]|2[0-3]):[0-5][0-9]$' },
            working_hours_end: { type: 'string', pattern: '^([01][0-9]|2[0-3]):[0-5][0-9]$' },
          },
        },
      },
      required: ['name', 'latitude', 'longitude', 'area_acres', 'state', 'district'],
    },
    field: {
      type: 'object',
      properties: {
        name: text(80),
        crop_name: text(80),
        growth_stage: { enum: OPTIONS.growth_stages },
        sown_on: date,
        expected_harvest_on: date,
        soil_type: { enum: OPTIONS.soil_types },
        irrigation_method: { enum: OPTIONS.irrigation_methods },
        area_acres: { type: 'number', exclusiveMinimum: 0, maximum: 100000 },
      },
      required: ['soil_type'],
    },
    soil: {
      type: 'object',
      properties: {
        source: { enum: ['lab', 'manual'], default: 'manual' },
        soil_ph: num(0, 14),
        nitrogen: num(0, 2000),
        phosphorus: num(0, 2000),
        potassium: num(0, 5000),
        soil_moisture: num(0, 100),
        electrical_conductivity: num(0, 30),
        soil_temperature: num(-20, 80),
      },
    },
    device: {
      type: 'object',
      properties: { token, label: text(80) },
      required: ['token'],
    },
  },
  required: ['farm', 'field'],
};

onboardingRoutes.post('/onboarding', authenticate, validate({ body: onboardingBody }), async (req, res) => {
  const { profile = {}, farm, field, soil, device } = req.body;
  if (field.sown_on && field.sown_on > new Date().toISOString().slice(0, 10)) {
    throw new HttpError(422, 'validation_failed', 'The sowing date cannot be in the future.');
  }

  const result = await transaction(async (db) => {
    if (profile.name || profile.phone || profile.language) {
      await db.query(
        `UPDATE users SET name = COALESCE($2, name), phone = COALESCE($3, phone), language = COALESCE($4, language)
          WHERE id = $1`,
        [req.user.id, profile.name?.trim() ?? null, profile.phone ?? null, profile.language ?? null],
      );
    }
    const createdFarm = await createFarm(db, req.user.id, farm);
    const createdField = await createField(db, createdFarm.id, {
      name: field.name || 'Main field',
      area_acres: field.area_acres ?? farm.area_acres,
      soil_type: field.soil_type,
      irrigation_method: field.irrigation_method,
      crop_name: field.crop_name,
      growth_stage: field.growth_stage,
      sown_on: field.sown_on,
      expected_harvest_on: field.expected_harvest_on,
    });

    let reading = null;
    const measured = soil && Object.keys(soil).some((k) => k !== 'source' && soil[k] !== undefined);
    if (measured) {
      reading = await insertReading(createdFarm.id, {
        ...soil, field_id: createdField.id, soil_type: field.soil_type, crop_type: field.crop_name,
      }, db);
    }
    let createdDevice = null;
    if (device?.token) {
      const { rows } = await db.query(
        `INSERT INTO blynk_tokens (farm_id, token, label) VALUES ($1, $2, $3)
         RETURNING id, label, is_active, right(token, 4) AS token_hint`,
        [createdFarm.id, device.token, device.label ?? 'Soil probe'],
      );
      createdDevice = rows[0];
    }
    await db.query('UPDATE users SET onboarded_at = COALESCE(onboarded_at, now()) WHERE id = $1', [req.user.id]);
    return { farm: presentArea(createdFarm), field: createdField, soil: reading, device: createdDevice };
  }).catch((err) => {
    if (err.code === '23505' && String(err.constraint).includes('blynk')) {
      throw conflict('That device token is already registered to another farm.');
    }
    if (err.code === '23505' && err.constraint === 'uq_users_phone_active') {
      throw conflict('That phone number is already used by another account.');
    }
    throw err;
  });

  res.status(201).json(result);
});

/**
 * Demo account: a verified, fully onboarded farmer with a live Blynk probe.
 *
 *   npm run seed:demo
 *
 * Safe to run again: the user is reused (password reset to the demo one),
 * and the farm, field and device are only created when missing. Finishes
 * with a live sensor sync so the dashboard opens with real readings.
 *
 * Credentials come from the environment when set (DEMO_EMAIL, DEMO_PASSWORD,
 * DEMO_BLYNK_TOKEN); the defaults are for local development only.
 */

import { hashPassword } from '../modules/auth/security.js';
import { createFarm, createField } from '../modules/farms.js';
import { syncDevice } from '../modules/soil.js';
import { closePool, one, transaction } from './pool.js';

const EMAIL = (process.env.DEMO_EMAIL || 'demo@farmxpert.in').toLowerCase();
const PASSWORD = process.env.DEMO_PASSWORD || 'Demo@Farm2026';
const TOKEN = process.env.DEMO_BLYNK_TOKEN || 'PBrw14c3z0O1biZJaH258X9MGpW-FnCE';

async function main() {
  const passwordHash = await hashPassword(PASSWORD);

  const { user, farm } = await transaction(async (db) => {
    const account = (await db.query(
      `INSERT INTO users (name, email, password_hash, phone, language, role, email_verified, onboarded_at)
       VALUES ('Ramesh Patel', $1, $2, '+919876543210', 'en', 'farmer', true, now())
       ON CONFLICT (email) WHERE deleted_at IS NULL AND email IS NOT NULL DO UPDATE
         SET password_hash = EXCLUDED.password_hash, email_verified = true, phone = COALESCE(users.phone, EXCLUDED.phone),
             onboarded_at = COALESCE(users.onboarded_at, now()),
             failed_logins = 0, locked_until = NULL
       RETURNING id, name, email`,
      [EMAIL, passwordHash],
    )).rows[0];

    let demoFarm = (await db.query(
      'SELECT id, name FROM farms WHERE user_id = $1 AND deleted_at IS NULL ORDER BY created_at LIMIT 1',
      [account.id],
    )).rows[0];
    if (!demoFarm) {
      demoFarm = await createFarm(db, account.id, {
        name: 'Patel Farm', latitude: 21.17024, longitude: 72.83106, area_acres: 5,
        state: 'Gujarat', district: 'Surat', address: 'Surat, Gujarat', water_source: 'borewell',
        resources: { irrigation_available: true, labor_units_available: 3, equipment_available: ['sprayer', 'drip'] },
      });
      await createField(db, demoFarm.id, {
        name: 'Main field', area_acres: 5, soil_type: 'black_cotton', irrigation_method: 'drip',
        crop_name: 'cotton', growth_stage: 'flowering',
        sown_on: new Date(Date.now() - 95 * 86400000).toISOString().slice(0, 10),
      });
    }

    await db.query(
      `INSERT INTO blynk_tokens (farm_id, token, label)
       SELECT $1, $2, 'Soil probe'
        WHERE NOT EXISTS (SELECT 1 FROM blynk_tokens WHERE farm_id = $1 AND is_active)
       ON CONFLICT (token) DO NOTHING`,
      [demoFarm.id, TOKEN],
    );
    return { user: account, farm: demoFarm };
  });

  const device = await one('SELECT id FROM blynk_tokens WHERE farm_id = $1 AND is_active', [farm.id]);
  let sensor = 'no device on this farm (token belongs to another farm?)';
  if (device) {
    try {
      const out = await syncDevice(farm.id);
      sensor = { ...out.reading && pick(out.reading), dropped: out.dropped_channels };
    } catch (err) {
      sensor = `sync failed: ${err.message}`;
    }
  }

  console.log('\nDemo account ready');
  console.log('  email:    ', user.email);
  console.log('  password: ', PASSWORD);
  console.log('  farm:     ', farm.name, farm.id);
  console.log('  sensor:   ', sensor);
}

function pick(r) {
  const keys = ['air_temperature', 'air_humidity', 'soil_moisture', 'soil_temperature',
    'electrical_conductivity', 'soil_ph', 'nitrogen', 'phosphorus', 'potassium'];
  return Object.fromEntries(keys.filter((k) => r[k] != null).map((k) => [k, r[k]]));
}

main()
  .catch((err) => { console.error(err); process.exitCode = 1; })
  .finally(() => closePool());

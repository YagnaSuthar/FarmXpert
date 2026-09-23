import assert from 'node:assert/strict';
import { test } from 'node:test';

import { toReading } from '../src/clients/blynk.js';
import { normaliseRecord, parseDate } from '../src/clients/mandi.js';
import { buildAiRequest } from '../src/modules/chat/routes.js';
import { decodeCursor, encodeCursor, toPage } from '../src/lib/paging.js';
import { acresToHectares, hectaresToAcres, pointWkt } from '../src/lib/units.js';
import { validate } from '../src/lib/validate.js';

const ID = '3f2b8c1e-7d4a-4e9b-9c1a-2b3c4d5e6f70';

test('cursor round-trips and rejects tampering', () => {
  const at = new Date('2026-09-23T04:05:06.789Z');
  assert.deepEqual(decodeCursor(encodeCursor(at, ID)), { at, id: ID });
  assert.equal(decodeCursor('garbage'), null);
  assert.equal(decodeCursor(Buffer.from('2026-09-23|not-a-uuid').toString('base64url')), null);
  assert.equal(decodeCursor(undefined), null);
});

test('toPage uses the extra row to know about the next page', () => {
  const rows = [1, 2, 3].map((n) => ({ id: ID, at: new Date(n * 1000) }));
  const page = toPage(rows, 2, (r) => [r.at, r.id]);
  assert.equal(page.items.length, 2);
  assert.deepEqual(decodeCursor(page.nextCursor), { at: new Date(2000), id: ID });
  assert.equal(toPage(rows, 3, (r) => [r.at, r.id]).nextCursor, null);
});

test('units', () => {
  assert.ok(Math.abs(acresToHectares(2.47105) - 1) < 1e-9);
  assert.ok(Math.abs(hectaresToAcres(acresToHectares(7)) - 7) < 1e-9);
  assert.equal(pointWkt(21.17, 72.83), 'SRID=4326;POINT(72.83 21.17)', 'longitude first');
});

function run(middleware, req) {
  let error;
  middleware(req, {}, (err) => { error = err; });
  return error;
}

test('validation coerces, defaults, strips unknown fields and reports problems', () => {
  const mw = validate({
    body: { type: 'object', properties: { n: { type: 'integer' }, lang: { type: 'string', default: 'en' } }, required: ['n'] },
    query: { type: 'object', properties: { limit: { type: 'integer', default: 20 } } },
  });
  const req = { body: { n: '5', evil: 'x' }, query: { limit: '7', other: '1' } };
  assert.equal(run(mw, req), undefined);
  assert.deepEqual(req.body, { n: 5, lang: 'en' });
  assert.deepEqual(req.query, { limit: 7 });

  const bad = run(mw, { body: {}, query: {} });
  assert.equal(bad.status, 422);
  assert.match(bad.details[0].problem, /required/);
});

test('mandi: missing prices are null, never 0; dates parsed and checked', () => {
  const row = normaliseRecord({
    commodity: 'Wheat', market: 'Surat', arrival_date: '20/09/2026', min_price: '', max_price: '2600', modal_price: 'NR',
  });
  assert.deepEqual([row.minPrice, row.maxPrice, row.modalPrice, row.arrivalDate], [null, 2600, null, '2026-09-20']);
  assert.equal(row.variety, '');
  assert.equal(parseDate('31/02/2026'), null, 'impossible date');
  assert.equal(parseDate('2026-09-20'), '2026-09-20');
  assert.equal(normaliseRecord({ commodity: 'Wheat', arrival_date: '20/09/2026' }), null, 'no market');
  const inverted = normaliseRecord({ commodity: 'W', market: 'M', arrival_date: '2026-09-20', min_price: 50, max_price: 10, modal_price: 30 });
  assert.deepEqual([inverted.minPrice, inverted.maxPrice, inverted.modalPrice], [null, null, 30]);
});

test('blynk: pin map matches the firmware and a broken channel is dropped, not zeroed', () => {
  const { reading, dropped } = toReading({ V0: '41.5', V2: '99', V3: '120', V6: '1.2', V8: '' });
  assert.deepEqual(reading, { soil_moisture: 41.5, nitrogen: 120, electrical_conductivity: 1.2 });
  assert.deepEqual(dropped, ['soil_ph']);
});

test('AI request carries farm context and lets the farmer override the crop', () => {
  const request = buildAiRequest({
    body: { query: 'water today?', language: 'hi', crop: { name: 'cotton' } },
    requestId: 'req-12345678',
    farm: { id: ID, latitude: 21.17, longitude: 72.83, state: 'Gujarat', district: 'Surat', area_hectares: 2 },
    field: { id: ID, crop_name: 'wheat', growth_stage: 'tillering', soil_type: 'black', sown_on: null, area_hectares: 1.5 },
    soil: { soil_ph: 7.2, soil_moisture: 31, nitrogen: null, recorded_at: new Date('2026-09-23T00:00:00Z') },
    history: [{ role: 'farmer', content: 'hi' }],
  });
  assert.deepEqual(request.location, { lat: 21.17, lon: 72.83 });
  assert.deepEqual(request.soil, { soil_ph: 7.2, soil_moisture: 31, recorded_at: '2026-09-23T00:00:00.000Z', soil_type: 'black' });
  assert.equal(request.crop.name, 'cotton');
  assert.equal(request.crop.area_hectares, 1.5);
  assert.deepEqual(request.market, { state: 'Gujarat', district: 'Surat' });
  assert.equal(request.history.length, 1);

  const bare = buildAiRequest({ body: { query: 'hello' }, requestId: 'r-00000000', history: [] });
  assert.deepEqual(Object.keys(bare).sort(), ['explain', 'history', 'language', 'query', 'request_id']);
});

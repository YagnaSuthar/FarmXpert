/**
 * Blynk Cloud: read a farm's sensor virtual pins.
 *
 * The token is a credential. It goes into the query string because that is
 * Blynk's API, so the URL is never logged.
 */

import { readFile } from 'node:fs/promises';

import { config } from '../config/env.js';

// While the probe hardware is being built, BLYNK_MOCK=true serves static readings
// from this file instead of calling Blynk (same V0-V8 shape as the real API).
const MOCK_FILE = new URL('../data/sensor-mock.json', import.meta.url);

// Virtual pin to soil_data column, as the FarmXpert probe firmware publishes
// them (V0-V8). One place to change it.
export const PIN_MAP = Object.freeze({
  V0: 'air_temperature',          // deg C
  V1: 'air_humidity',             // %
  V2: 'soil_moisture',            // %
  V3: 'soil_temperature',         // deg C
  V4: 'electrical_conductivity',  // dS/m
  V5: 'soil_ph',
  V6: 'nitrogen',                 // mg/kg
  V7: 'phosphorus',               // mg/kg
  V8: 'potassium',                // mg/kg
});

// Values outside these are a broken channel: dropped, not stored, matching
// the soil_data range checks so one bad pin cannot reject the whole reading.
const RANGES = {
  soil_moisture: [0, 100],
  soil_temperature: [-20, 80],
  soil_ph: [0.5, 14],             // 0 = electrode not connected
  electrical_conductivity: [0, 30],
  nitrogen: [0, 2000],
  phosphorus: [0, 2000],
  potassium: [0, 5000],
  air_temperature: [-40, 60],
  air_humidity: [0, 100],
};

/**
 * The bare token from whatever was pasted: the token itself, a Blynk API link
 * (".../get?token=XYZ&V0"), or a token with a pin stuck on ("XYZ&V8").
 */
export function cleanToken(input) {
  const text = String(input ?? '').trim();
  const fromLink = text.match(/[?&]token=([A-Za-z0-9_-]+)/);
  if (fromLink) return fromLink[1];
  return text.split(/[&?\s]/)[0];
}

export async function readPins(token, { timeoutMs = 8000 } = {}) {
  if (config.blynk.mock) {
    const pins = JSON.parse(await readFile(MOCK_FILE, 'utf8'));
    return toReading(pins);
  }
  const url = new URL(config.blynk.baseUrl);
  url.searchParams.set('token', token);
  for (const pin of Object.keys(PIN_MAP)) url.searchParams.append(pin, '');

  const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
  if (response.status === 400 || response.status === 401) {
    const err = new Error('Blynk rejected the device token.');
    err.code = 'invalid_token';
    throw err;
  }
  if (!response.ok) throw new Error(`Blynk answered ${response.status}`);
  return toReading(await response.json());
}

/** Map a Blynk pin response to soil_data columns, clamping bad channels to absent. */
export function toReading(pins) {
  const reading = {};
  const dropped = [];
  for (const [pin, column] of Object.entries(PIN_MAP)) {
    const value = Number(pins?.[pin]);
    if (pins?.[pin] === undefined || pins?.[pin] === '' || !Number.isFinite(value)) continue;
    const [lo, hi] = RANGES[column];
    if (value < lo || value > hi) dropped.push(column);
    else reading[column] = value;
  }
  return { reading, dropped };
}

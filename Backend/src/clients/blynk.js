/**
 * Blynk Cloud: read a farm's sensor virtual pins.
 *
 * The token is a credential. It goes into the query string because that is
 * Blynk's API, so the URL is never logged.
 */

import { config } from '../config/env.js';

// Virtual pin to soil_data column, as the probe firmware publishes them (the
// same map the old Python extractor used). One place to change it.
export const PIN_MAP = Object.freeze({
  V0: 'soil_moisture',
  V1: 'soil_temperature',
  V2: 'soil_ph',
  V3: 'nitrogen',
  V4: 'phosphorus',
  V5: 'potassium',
  V6: 'electrical_conductivity',
  V7: 'air_temperature',
  V8: 'air_humidity',
});

// Values outside these are a broken channel: dropped, not stored, matching
// the soil_data range checks so one bad pin cannot reject the whole reading.
const RANGES = {
  soil_moisture: [0, 100],
  soil_temperature: [-20, 80],
  soil_ph: [0, 14],
  electrical_conductivity: [0, 30],
  nitrogen: [0, 2000],
  phosphorus: [0, 2000],
  potassium: [0, 5000],
  air_temperature: [-40, 60],
  air_humidity: [0, 100],
};

export async function readPins(token, { timeoutMs = 8000 } = {}) {
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

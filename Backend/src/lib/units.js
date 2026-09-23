/**
 * Units and geometry helpers.
 *
 * One unit is stored in the database - hectares, metres, UTC - and
 * everything else is a display conversion done here. That is how an acre
 * never gets added to a hectare three screens later.
 */

export const ACRES_PER_HECTARE = 2.47105;

export function acresToHectares(acres) {
  return acres === null || acres === undefined ? null : round(acres / ACRES_PER_HECTARE, 3);
}

export function hectaresToAcres(hectares) {
  return hectares === null || hectares === undefined ? null : round(Number(hectares) * ACRES_PER_HECTARE, 3);
}

/**
 * EWKT for a PostGIS geography point. Longitude comes first: that is the WKT
 * order, and swapping it puts a Gujarat farm in the Indian Ocean.
 */
export function pointWkt(latitude, longitude) {
  return `SRID=4326;POINT(${Number(longitude)} ${Number(latitude)})`;
}

export function round(value, places = 2) {
  const factor = 10 ** places;
  return Math.round(Number(value) * factor) / factor;
}

/** Postgres NUMERIC arrives as a string; turn it into a number or null. */
export function num(value) {
  if (value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

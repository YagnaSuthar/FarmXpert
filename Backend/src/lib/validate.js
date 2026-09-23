/**
 * Request validation (Ajv).
 *
 * Each schema is compiled to a plain function once, at startup, which makes
 * Ajv the fastest JSON validator available for Node - validation costs
 * microseconds per request. `coerceTypes` turns "20" in a query string into
 * 20, and `removeAdditional` drops unknown fields, so a handler only ever
 * sees fields it declared.
 */

import Ajv from 'ajv';
import addFormats from 'ajv-formats';

import { unprocessable } from './errors.js';

const ajv = new Ajv({
  allErrors: true,
  coerceTypes: true,
  removeAdditional: 'all',
  useDefaults: true,
  strict: false,
});
addFormats(ajv);

/**
 * Middleware that validates `req.body`, `req.query` and/or `req.params`
 * against the given schemas and replaces them with the cleaned values.
 */
export function validate({ body, query, params } = {}) {
  const checks = [
    body && ['body', ajv.compile(body)],
    query && ['query', ajv.compile(query)],
    params && ['params', ajv.compile(params)],
  ].filter(Boolean);

  return function validator(req, res, next) {
    for (const [part, check] of checks) {
      // Express 5 exposes req.query as a getter; validate a copy, then pin it.
      const value = part === 'query' ? { ...req.query } : (req[part] ?? {});
      if (!check(value)) {
        return next(unprocessable(`The request ${part} is invalid.`, formatErrors(check.errors, part)));
      }
      if (part === 'query') {
        Object.defineProperty(req, 'query', { value, writable: true, configurable: true });
      } else {
        req[part] = value;
      }
    }
    return next();
  };
}

function formatErrors(errors, part) {
  return (errors || []).slice(0, 10).map((e) => ({
    field: `${part}${e.instancePath.replaceAll('/', '.')}` || part,
    problem: e.message,
  }));
}

// ── shared schema fragments ─────────────────────────────────────────────────

export const uuid = { type: 'string', format: 'uuid' };
export const idParam = {
  type: 'object',
  properties: { id: uuid },
  required: ['id'],
};
export const pageQuery = {
  limit: { type: 'integer', minimum: 1, maximum: 100, default: 20 },
  cursor: { type: 'string', maxLength: 200 },
};
export const latitude = { type: 'number', minimum: -90, maximum: 90 };
export const longitude = { type: 'number', minimum: -180, maximum: 180 };

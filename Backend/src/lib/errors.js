/**
 * HTTP errors and the one place they are turned into responses.
 *
 * Handlers throw; they never build error responses themselves. The error
 * middleware then gives every failure the same shape, and an unexpected
 * error is logged in full with the request id while the client sees only a
 * code and a sentence - never a stack trace, a SQL message or a file path.
 */

import { logger } from './logger.js';

export class HttpError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export const badRequest = (message, details) =>
  new HttpError(400, 'bad_request', message, details);
export const unauthorized = (message = 'Authentication required.') =>
  new HttpError(401, 'unauthorized', message);
export const notFound = (what = 'Resource') => new HttpError(404, 'not_found', `${what} not found.`);
export const conflict = (message) => new HttpError(409, 'conflict', message);
export const unprocessable = (message, details) =>
  new HttpError(422, 'validation_failed', message, details);
export const unavailable = (message) => new HttpError(503, 'unavailable', message);

// PostgreSQL error codes that are the client's fault, mapped to a clear answer.
const PG_ERRORS = {
  '23505': [409, 'conflict', 'That already exists.'],
  '23503': [409, 'conflict', 'A referenced record does not exist.'],
  '23514': [422, 'validation_failed', 'A value is outside its allowed range.'],
  '22P02': [400, 'bad_request', 'A value has the wrong format.'],
  '57014': [503, 'timeout', 'The database took too long; please try again.'],
};

export function notFoundHandler(req, res) {
  res.status(404).json({ error: { code: 'not_found', message: 'Route not found.' } });
}

// eslint-disable-next-line no-unused-vars
export function errorHandler(err, req, res, next) {
  let status = 500;
  let body = { code: 'internal', message: 'Something went wrong. Please try again.' };

  if (err instanceof HttpError) {
    status = err.status;
    body = { code: err.code, message: err.message, ...(err.details ? { details: err.details } : {}) };
  } else if (err?.type === 'entity.parse.failed') {
    status = 400;
    body = { code: 'bad_request', message: 'The request body is not valid JSON.' };
  } else if (err?.type === 'entity.too.large') {
    status = 413;
    body = { code: 'too_large', message: 'The request body is too large.' };
  } else if (err?.code && PG_ERRORS[err.code]) {
    const [pgStatus, code, message] = PG_ERRORS[err.code];
    status = pgStatus;
    body = { code, message, ...(err.constraint ? { constraint: err.constraint } : {}) };
  }

  if (status >= 500) {
    (req.log || logger).error({ err, requestId: req.id }, 'Request failed');
  }
  res.status(status).json({ error: { ...body, requestId: req.id } });
}

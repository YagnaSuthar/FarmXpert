/**
 * Structured logging (pino).
 *
 * Pino writes JSON asynchronously and is several times faster than console
 * logging, which matters on a hot path that logs every request. Secrets and
 * farmer personal data are redacted by path, so a log shipped to an
 * aggregator never carries a token, a phone number or a farmer's question.
 */

import pino from 'pino';

import { config } from '../config/env.js';

export const logger = pino({
  level: config.logLevel,
  base: { service: 'farmxpert-backend' },
  timestamp: pino.stdTimeFunctions.isoTime,
  redact: {
    paths: [
      'req.headers.authorization',
      'req.headers["x-api-key"]',
      'req.headers["x-internal-key"]',
      'req.headers.cookie',
      '*.token',
      '*.password',
      '*.phone',
      '*.query',          // a farmer's question is personal data
      '*.content',
      'err.config',
    ],
    censor: '[redacted]',
  },
  ...(config.production
    ? {}
    : { transport: { target: 'pino-pretty', options: { singleLine: true } } }),
});

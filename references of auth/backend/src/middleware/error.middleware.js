const logger = require('../utils/logger');

/**
 * Centralized error handling middleware.
 *
 * SECURITY: Never leaks SQL errors, stack traces, secrets,
 * password hashes, OTPs, or internal implementation details to clients.
 *
 * In development, additional error details are logged to console.
 * In production, clients receive only generic error messages.
 */

// eslint-disable-next-line no-unused-vars
function errorMiddleware(err, req, res, next) {
  // Log the full error internally (sanitized by logger)
  logger.error('Unhandled error', {
    message: err.message,
    stack: process.env.NODE_ENV !== 'production' ? err.stack : undefined,
    method: req.method,
    url: req.originalUrl,
    ip: req.ip,
  });

  // Determine status code
  const statusCode = err.statusCode || err.status || 500;

  // Build client-safe response
  const response = {
    success: false,
    message: statusCode >= 500
      ? 'An internal server error occurred'
      : err.message || 'Something went wrong',
  };

  // In development, include the error type (but never the stack or SQL)
  if (process.env.NODE_ENV !== 'production' && statusCode < 500) {
    response.error = err.message;
  }

  return res.status(statusCode).json(response);
}

module.exports = errorMiddleware;

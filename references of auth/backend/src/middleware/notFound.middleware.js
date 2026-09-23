const { error } = require('../utils/response');

/**
 * 404 handler for unmatched routes.
 * Must be mounted AFTER all route registrations.
 */
function notFoundMiddleware(req, res) {
  return error(res, `Route not found: ${req.method} ${req.originalUrl}`, 404);
}

module.exports = notFoundMiddleware;

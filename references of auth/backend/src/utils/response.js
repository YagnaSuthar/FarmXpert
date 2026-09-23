/**
 * Standardized API response helpers.
 * All API responses follow the shape:
 * {
 *   success: boolean,
 *   message: string,
 *   data: any | undefined
 * }
 */

/**
 * Send a successful response.
 * @param {import('express').Response} res
 * @param {string} message
 * @param {*} [data]
 * @param {number} [statusCode=200]
 */
function success(res, message, data, statusCode = 200) {
  const response = { success: true, message };
  if (data !== undefined) response.data = data;
  return res.status(statusCode).json(response);
}

/**
 * Send a created (201) response.
 * @param {import('express').Response} res
 * @param {string} message
 * @param {*} [data]
 */
function created(res, message, data) {
  return success(res, message, data, 201);
}

/**
 * Send an error response.
 * @param {import('express').Response} res
 * @param {string} message
 * @param {number} [statusCode=400]
 * @param {*} [errors]
 */
function error(res, message, statusCode = 400, errors) {
  const response = { success: false, message };
  if (errors !== undefined) response.errors = errors;
  return res.status(statusCode).json(response);
}

module.exports = { success, created, error };

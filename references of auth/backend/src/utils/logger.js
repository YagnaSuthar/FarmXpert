/**
 * Simple structured logger.
 * Sanitizes sensitive fields before output.
 *
 * In production, this should be replaced with a proper
 * logging library (winston, pino) that supports log levels,
 * file rotation, and structured JSON output.
 */

const SENSITIVE_FIELDS = [
  'password',
  'password_hash',
  'passwordHash',
  'pepper',
  'otp',
  'otp_hash',
  'otpHash',
  'token',
  'accessToken',
  'refreshToken',
  'sessionId',
  'secret',
  'authorization',
];

/**
 * Deep-clone and redact sensitive fields from an object.
 * @param {*} data
 * @returns {*}
 */
function sanitize(data) {
  if (!data || typeof data !== 'object') return data;

  if (Array.isArray(data)) {
    return data.map(sanitize);
  }

  const sanitized = {};
  for (const [key, value] of Object.entries(data)) {
    if (SENSITIVE_FIELDS.includes(key.toLowerCase())) {
      sanitized[key] = '[REDACTED]';
    } else if (typeof value === 'object' && value !== null) {
      sanitized[key] = sanitize(value);
    } else {
      sanitized[key] = value;
    }
  }
  return sanitized;
}

function formatMessage(level, message, meta) {
  const timestamp = new Date().toISOString();
  const metaStr = meta ? ` ${JSON.stringify(sanitize(meta))}` : '';
  return `[${timestamp}] [${level}] ${message}${metaStr}`;
}

const logger = {
  info(message, meta) {
    console.log(formatMessage('INFO', message, meta));
  },

  warn(message, meta) {
    console.warn(formatMessage('WARN', message, meta));
  },

  error(message, meta) {
    console.error(formatMessage('ERROR', message, meta));
  },

  debug(message, meta) {
    if (process.env.NODE_ENV !== 'production') {
      console.debug(formatMessage('DEBUG', message, meta));
    }
  },
};

module.exports = logger;

/**
 * Configuration, read once and validated at boot.
 *
 * A missing or malformed setting fails at startup with a message naming the
 * variable - not twenty minutes later inside a farmer's request. The result
 * is frozen, so nothing can change configuration at runtime by accident.
 */

const env = process.env;

function int(name, fallback, { min = -Infinity, max = Infinity } = {}) {
  const raw = env[name];
  if (raw === undefined || raw === '') return fallback;
  const value = Number.parseInt(raw, 10);
  if (!Number.isFinite(value) || value < min || value > max) {
    throw new Error(`${name} must be an integer between ${min} and ${max}, got "${raw}"`);
  }
  return value;
}

function bool(name, fallback) {
  const raw = env[name];
  if (raw === undefined || raw === '') return fallback;
  return ['1', 'true', 'yes', 'on'].includes(raw.toLowerCase());
}

function list(name, fallback) {
  const raw = env[name];
  if (!raw) return fallback;
  return raw.split(',').map((item) => item.trim()).filter(Boolean);
}

const nodeEnv = env.NODE_ENV || 'development';
const production = nodeEnv === 'production';

export const config = Object.freeze({
  env: nodeEnv,
  production,
  port: int('PORT', 4000, { min: 1, max: 65535 }),
  logLevel: env.LOG_LEVEL || (production ? 'info' : 'debug'),
  // Size of the in-process worker pool. 0 means "one per CPU".
  workers: int('WEB_CONCURRENCY', 1, { min: 0, max: 64 }),

  db: Object.freeze({
    url: env.DATABASE_URL || '',
    poolMax: int('DB_POOL_MAX', 20, { min: 1, max: 200 }),
    statementTimeoutMs: int('DB_STATEMENT_TIMEOUT_MS', 15000, { min: 100 }),
    idleTimeoutMs: int('DB_IDLE_TIMEOUT_MS', 30000, { min: 1000 }),
    ssl: (env.DB_SSL || (production ? 'require' : 'disable')).toLowerCase(),
  }),

  ai: Object.freeze({
    url: (env.AI_BACKEND_URL || 'http://127.0.0.1:8000').replace(/\/+$/, ''),
    timeoutMs: int('AI_TIMEOUT_MS', 35000, { min: 1000 }),
    // A streamed answer (and a voice answer, with speech both ways) runs longer.
    streamTimeoutMs: int('AI_STREAM_TIMEOUT_MS', 90000, { min: 5000 }),
    internalKey: env.INTERNAL_API_KEY || '',
  }),

  adminKey: env.ADMIN_API_KEY || '',
  corsOrigins: list('CORS_ORIGINS', ['http://localhost:3000']),

  mandi: Object.freeze({
    apiKey: env.DATA_GOV_API_KEY || '',
    resourceId: env.MANDI_RESOURCE_ID || '9ef84268-d588-465a-a308-a864a43d0070',
    commodities: list('MANDI_COMMODITIES', ['Wheat', 'Rice', 'Tomato', 'Onion', 'Potato']),
    cron: env.MANDI_CRON || '15 * * * *',
  }),

  blynk: Object.freeze({
    // Regional server: a token only works on the region its device lives in.
    baseUrl: (env.BLYNK_BASE_URL || 'https://blr1.blynk.cloud/external/api/get').replace(/\/+$/, ''),
    syncCron: env.SENSOR_SYNC_CRON || '*/15 * * * *',
    // Static readings from src/data/sensor-mock.json instead of the real probe.
    mock: env.BLYNK_MOCK === 'true',
  }),

  lifecycle: Object.freeze({
    archiveUri: env.ARCHIVE_URI || 'file://./archive',
    cron: env.LIFECYCLE_CRON || '30 2 * * *',
  }),

  tokens: Object.freeze({
    // Per farmer per local day, across every model. 0 = no limit. A typical
    // question costs 3-5k tokens, so the default allows ~15 a day.
    dailyLimit: int('TOKEN_DAILY_LIMIT', 60000, { min: 0 }),
    timezone: timezone('TOKEN_DAY_TIMEZONE', 'Asia/Kolkata'),
    // Price per 1M tokens: {"model": {"input": 0.23, "output": 0.40}}. Models
    // without a price cost 0 and are reported as unpriced.
    prices: prices('TOKEN_PRICES'),
    currency: env.TOKEN_PRICE_CURRENCY || 'USD',
    retentionDays: int('TOKEN_USAGE_RETENTION_DAYS', 730, { min: 30 }),
  }),

  voice: Object.freeze({
    maxBytes: int('VOICE_MAX_BYTES', 2 * 1024 * 1024, { min: 10 * 1024, max: 25 * 1024 * 1024 }),
    maxSeconds: int('VOICE_MAX_SECONDS', 60, { min: 5, max: 600 }),
    // Speech minutes per farmer per local day, on top of the token allowance
    // (speech is billed per second, not per token). 0 = no limit.
    dailySeconds: int('VOICE_DAILY_SECONDS', 900, { min: 0 }),
  }),

  // Burst guard per user (or IP) per minute. 0 disables.
  rateLimit: Object.freeze({
    chatPerMinute: int('RATE_LIMIT_CHAT_PER_MIN', 20, { min: 0 }),
    voicePerMinute: int('RATE_LIMIT_VOICE_PER_MIN', 8, { min: 0 }),
  }),

  auth: Object.freeze({
    // Dev-only fallbacks keep `npm run dev` working out of the box; production
    // refuses to start without real secrets (assertProductionReady).
    jwtSecret: env.JWT_SECRET || 'dev-only-jwt-secret-change-me',
    passwordPepper: env.PASSWORD_PEPPER || 'dev-only-pepper-change-me',
    bcryptRounds: int('BCRYPT_ROUNDS', 12, { min: 10, max: 15 }),
    accessTtlSeconds: int('ACCESS_TOKEN_TTL_SECONDS', 900, { min: 60, max: 3600 }),
    refreshDays: int('REFRESH_TOKEN_DAYS', 30, { min: 1, max: 90 }),
    // Admin accounts get short refresh windows and no "remember me".
    privilegedRefreshHours: int('PRIVILEGED_REFRESH_HOURS', 12, { min: 1, max: 72 }),
    otpMinutes: int('OTP_EXPIRES_MINUTES', 10, { min: 2, max: 60 }),
    otpMaxAttempts: int('OTP_MAX_ATTEMPTS', 5, { min: 3, max: 10 }),
    captchaMinutes: int('CAPTCHA_EXPIRES_MINUTES', 5, { min: 1, max: 30 }),
    // Per IP per 15 minutes, for login/register and for code endpoints.
    rateLimitPer15Min: int('AUTH_RATE_LIMIT', 20, { min: 1 }),
    cookieSecure: bool('COOKIE_SECURE', production),
    cookieDomain: env.COOKIE_DOMAIN || undefined,
    appUrl: (env.APP_URL || 'http://localhost:3000').replace(/\/+$/, ''),
  }),

  smtp: Object.freeze({
    host: env.SMTP_HOST || '',
    port: int('SMTP_PORT', 587, { min: 1, max: 65535 }),
    user: env.SMTP_USER || '',
    pass: env.SMTP_PASS || '',
    fromName: env.SMTP_FROM_NAME || 'FarmXpert',
    fromEmail: env.SMTP_FROM || env.SMTP_USER || '',
  }),

  jobsEnabled: bool('JOBS_ENABLED', true),
});

function timezone(name, fallback) {
  const value = env[name] || fallback;
  try {
    new Intl.DateTimeFormat('en', { timeZone: value });
  } catch {
    throw new Error(`${name} is not a valid IANA time zone: "${value}"`);
  }
  return value;
}

function prices(name) {
  const raw = env[name];
  if (!raw) return Object.freeze({});
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error(`${name} must be JSON like {"model":{"input":0.2,"output":0.4}}`);
  }
  // Tokens: {"input": per 1M, "output": per 1M}. Speech-to-text:
  // {"per_minute": x}. Text-to-speech: {"per_1m_characters": x}. Keys may combine.
  const KEYS = ['input', 'output', 'per_minute', 'per_1m_characters'];
  for (const [model, p] of Object.entries(parsed)) {
    const keys = Object.keys(p || {});
    if (!keys.length || keys.some((k) => !KEYS.includes(k))) {
      throw new Error(`${name}: "${model}" must use only ${KEYS.join(', ')}`);
    }
    for (const key of keys) {
      if (!(Number.isFinite(p[key]) && p[key] >= 0)) {
        throw new Error(`${name}: "${model}".${key} must be a non-negative number`);
      }
    }
  }
  return Object.freeze(parsed);
}

/** Settings a production deployment must not run without. */
export function assertProductionReady() {
  if (!config.production) return;
  const missing = [];
  if (!config.db.url) missing.push('DATABASE_URL');
  if (!config.ai.internalKey) missing.push('INTERNAL_API_KEY');
  if (!config.adminKey) missing.push('ADMIN_API_KEY');
  if (!env.JWT_SECRET || env.JWT_SECRET.length < 32) missing.push('JWT_SECRET (32+ chars)');
  if (!env.PASSWORD_PEPPER || env.PASSWORD_PEPPER.length < 32) missing.push('PASSWORD_PEPPER (32+ chars)');
  if (!config.smtp.host) missing.push('SMTP_HOST');
  if (missing.length) {
    throw new Error(`Refusing to start in production without: ${missing.join(', ')}`);
  }
}

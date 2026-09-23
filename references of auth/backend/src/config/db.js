const { Pool } = require('pg');
const { env } = require('./env');
const logger = require('../utils/logger');

/**
 * PostgreSQL connection pool.
 * Uses pg.Pool for connection management and automatic reconnection.
 */
const pool = new Pool({
  host: env.db.host,
  port: env.db.port,
  database: env.db.name,
  user: env.db.user,
  password: env.db.password,
  max: 20,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
});

// Log pool errors (don't crash the process)
pool.on('error', (err) => {
  logger.error('Unexpected PostgreSQL pool error', { error: err.message });
});

/**
 * Test the database connection.
 * @returns {Promise<boolean>}
 */
async function testConnection() {
  let client;
  try {
    client = await pool.connect();
    const result = await client.query('SELECT NOW() AS current_time');
    logger.info('PostgreSQL connected successfully', {
      database: env.db.name,
      host: env.db.host,
      time: result.rows[0].current_time,
    });
    return true;
  } catch (err) {
    logger.error('PostgreSQL connection failed', {
      error: err.message,
      host: env.db.host,
      database: env.db.name,
    });
    return false;
  } finally {
    if (client) client.release();
  }
}

/**
 * Gracefully close all pool connections.
 */
async function closePool() {
  try {
    await pool.end();
    logger.info('PostgreSQL pool closed');
  } catch (err) {
    logger.error('Error closing PostgreSQL pool', { error: err.message });
  }
}

module.exports = { pool, testConnection, closePool };

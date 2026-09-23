const { env, validateEnv } = require('./config/env');
const { testConnection, closePool } = require('./config/db');
const logger = require('./utils/logger');
const app = require('./app');

/**
 * Server Entry Point
 *
 * 1. Validates environment variables
 * 2. Tests PostgreSQL connection
 * 3. Starts HTTP server
 * 4. Handles graceful shutdown
 */

async function startServer() {
  // Validate environment variables (exits on critical missing vars)
  validateEnv();

  // Test database connection
  const dbConnected = await testConnection();
  if (!dbConnected) {
    logger.error('Cannot start server without database connection');
    process.exit(1);
  }

  // Start HTTP server
  const server = app.listen(env.port, () => {
    logger.info(`Server started`, {
      port: env.port,
      environment: env.nodeEnv,
      url: `http://localhost:${env.port}`,
    });
    logger.info('Available routes:', {
      health: `GET  /api/health`,
      auth: `POST /api/auth/*`,
    });
  });

  // ─── Graceful Shutdown ──────────────────────────────────
  const shutdown = async (signal) => {
    logger.info(`${signal} received — shutting down gracefully`);

    server.close(async () => {
      logger.info('HTTP server closed');
      await closePool();
      logger.info('Shutdown complete');
      process.exit(0);
    });

    // Force shutdown after 10 seconds
    setTimeout(() => {
      logger.error('Forced shutdown after timeout');
      process.exit(1);
    }, 10000);
  };

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));

  // Handle unhandled rejections
  process.on('unhandledRejection', (reason) => {
    logger.error('Unhandled Promise Rejection', { reason: String(reason) });
  });

  // Handle uncaught exceptions
  process.on('uncaughtException', (err) => {
    logger.error('Uncaught Exception', { error: err.message, stack: err.stack });
    process.exit(1);
  });
}

startServer();

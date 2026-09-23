/**
 * Process entry point.
 *
 * WEB_CONCURRENCY > 1 forks that many workers (0 = one per CPU) sharing the
 * port; Node is single-threaded, so this is how one machine uses all its
 * cores. Only the first worker runs the background jobs (their advisory
 * locks would make duplicates harmless, but idle schedulers are waste).
 *
 * Shutdown is graceful: stop accepting, let in-flight requests finish, wait
 * for pending turn recordings, then close the pool.
 */

import cluster from 'node:cluster';
import { availableParallelism } from 'node:os';

import { createApp } from './app.js';
import { assertProductionReady, config } from './config/env.js';
import { closePool } from './db/pool.js';
import { startScheduler, stopScheduler } from './jobs/scheduler.js';
import { logger } from './lib/logger.js';
import { drainPendingTurns } from './modules/chat/routes.js';

assertProductionReady();

const workers = config.workers === 0 ? availableParallelism() : config.workers;

if (workers > 1 && cluster.isPrimary) {
  logger.info({ workers }, 'Starting workers');
  const indexOf = new Map();
  const fork = (i) => indexOf.set(cluster.fork({ FARMXPERT_WORKER_INDEX: String(i) }).id, i);
  for (let i = 0; i < workers; i += 1) fork(i);
  cluster.on('exit', (worker, code, signal) => {
    const index = indexOf.get(worker.id);
    indexOf.delete(worker.id);
    if (signal === 'SIGTERM' || signal === 'SIGINT' || code === 0) return;
    logger.error({ pid: worker.process.pid, code, signal }, 'Worker died; replacing it');
    fork(index);
  });
} else {
  const server = createApp().listen(config.port, () => {
    logger.info({ port: config.port, env: config.env }, 'FarmXpert backend listening');
  });
  // Longer than a typical load balancer's idle timeout, so it closes first.
  server.keepAliveTimeout = 65_000;
  server.headersTimeout = 66_000;

  if ((process.env.FARMXPERT_WORKER_INDEX ?? '0') === '0') startScheduler();

  let closing = false;
  const shutdown = async (signal) => {
    if (closing) return;
    closing = true;
    logger.info({ signal }, 'Shutting down');
    const force = setTimeout(() => process.exit(1), 25_000);
    force.unref();
    stopScheduler();
    await new Promise((resolve) => server.close(resolve));
    await drainPendingTurns();
    await closePool();
    process.exit(0);
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
  process.on('unhandledRejection', (err) => logger.error({ err }, 'Unhandled rejection'));
}

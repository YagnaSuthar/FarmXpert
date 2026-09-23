/**
 * Background jobs on a cron schedule.
 *
 * Every instance may run the scheduler; a PostgreSQL advisory lock per job
 * makes sure only one of them actually runs each tick, so scaling to four
 * instances does not ingest prices four times.
 */

import cron from 'node-cron';

import { config } from '../config/env.js';
import { mandiConfigured } from '../clients/mandi.js';
import { databaseConfigured, getPool } from '../db/pool.js';
import { logger } from '../lib/logger.js';
import { ingestMandiPrices } from '../modules/market.js';
import { runLifecycle } from './storageLifecycle.js';

const LOCKS = { mandi: 7261442911, lifecycle: 7261442912 };

/** Run `work` only if this instance wins the job's lock. Returns null if another holds it. */
export async function withJobLock(name, work) {
  const client = await getPool().connect();
  try {
    const { rows } = await client.query('SELECT pg_try_advisory_lock($1) AS got', [LOCKS[name]]);
    if (!rows[0].got) return null;
    try {
      return await work();
    } finally {
      await client.query('SELECT pg_advisory_unlock($1)', [LOCKS[name]]);
    }
  } finally {
    client.release();
  }
}

export const jobs = {
  mandi: () => ingestMandiPrices(config.mandi.commodities),
  lifecycle: () => runLifecycle(),
};

const tasks = [];

export function startScheduler() {
  if (!config.jobsEnabled || !databaseConfigured()) {
    logger.info('Background jobs disabled');
    return;
  }
  const schedule = (name, expression) => {
    tasks.push(cron.schedule(expression, () => {
      withJobLock(name, jobs[name])
        .then((result) => result !== null && logger.info({ job: name, result }, 'Job finished'))
        .catch((err) => logger.error({ err, job: name }, 'Job failed'));
    }, { timezone: 'UTC' }));
  };
  if (mandiConfigured()) schedule('mandi', config.mandi.cron);
  else logger.warn('DATA_GOV_API_KEY is not set; mandi ingestion is off');
  schedule('lifecycle', config.lifecycle.cron);
}

export function stopScheduler() {
  for (const task of tasks.splice(0)) task.stop();
}

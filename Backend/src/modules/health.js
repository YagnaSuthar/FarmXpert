import { Router } from 'express';

import { ai } from '../clients/ai.js';
import { databaseConfigured, query } from '../db/pool.js';

export const healthRoutes = Router();

// Liveness: the process is up. Never touches a dependency, so a database
// blip cannot make an orchestrator restart every instance at once.
healthRoutes.get('/health', (req, res) => {
  res.json({ status: 'ok', uptime_s: Math.round(process.uptime()) });
});

// Readiness: can this instance serve a farmer right now.
healthRoutes.get('/ready', async (req, res) => {
  const [database, advisory] = await Promise.all([
    databaseConfigured()
      ? query('SELECT 1').then(() => 'ok', () => 'down')
      : Promise.resolve('not_configured'),
    ai.health().then(() => 'ok', () => 'down'),
  ]);
  const ready = database === 'ok';
  res.status(ready ? 200 : 503).json({ status: ready ? 'ready' : 'degraded', database, advisory });
});

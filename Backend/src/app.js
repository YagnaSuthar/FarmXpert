/**
 * The Express application, without listening. Tests mount it on an
 * ephemeral port; server.js runs it for real.
 */

import { randomUUID } from 'node:crypto';

import compression from 'compression';
import cookieParser from 'cookie-parser';
import cors from 'cors';
import express from 'express';
import helmet from 'helmet';
import { pinoHttp } from 'pino-http';

import { config } from './config/env.js';
import { errorHandler, notFoundHandler } from './lib/errors.js';
import { logger } from './lib/logger.js';
import { adminRoutes } from './modules/admin.js';
import { authRoutes } from './modules/auth/routes.js';
import { onboardingRoutes } from './modules/onboarding.js';
import { chatRoutes } from './modules/chat/routes.js';
import { farmRoutes } from './modules/farms.js';
import { healthRoutes } from './modules/health.js';
import { marketRoutes } from './modules/market.js';
import { planRoutes } from './modules/plans.js';
import { soilRoutes } from './modules/soil.js';
import { usageRoutes } from './modules/usage.js';
import { userRoutes } from './modules/users.js';

export function createApp() {
  const app = express();
  app.disable('x-powered-by');
  // ETags hash every JSON body; these responses are per-farmer and uncached.
  app.set('etag', false);
  app.set('trust proxy', 1);

  app.use(helmet());
  // credentials: the refresh cookie must travel with /auth/refresh.
  app.use(cors({ origin: config.corsOrigins, credentials: true, maxAge: 600 }));
  app.use(compression({ threshold: 1024 }));
  app.use(pinoHttp({
    logger,
    genReqId: (req, res) => {
      const supplied = req.headers['x-request-id'];
      const id = typeof supplied === 'string' && /^[A-Za-z0-9_.:-]{8,64}$/.test(supplied) ? supplied : randomUUID();
      res.setHeader('x-request-id', id);
      return id;
    },
    // Health probes every few seconds would drown the real traffic.
    autoLogging: { ignore: (req) => req.url === '/health' },
    // One short line per request: headers are noise, and slow to serialise.
    serializers: {
      req: (req) => ({ id: req.id, method: req.method, url: req.url?.split('?')[0] }),
      res: (res) => ({ status: res.statusCode }),
    },
    customSuccessMessage: (req, res) => `${req.method} ${req.url?.split('?')[0]} ${res.statusCode}`,
  }));
  app.use(express.json({ limit: '256kb' }));
  app.use(cookieParser());

  app.use(healthRoutes);
  const api = express.Router();
  api.use(authRoutes, onboardingRoutes, userRoutes, farmRoutes, soilRoutes, planRoutes, marketRoutes,
    chatRoutes, usageRoutes, adminRoutes);
  app.use('/api/v1', api);

  app.use(notFoundHandler);
  app.use(errorHandler);
  return app;
}

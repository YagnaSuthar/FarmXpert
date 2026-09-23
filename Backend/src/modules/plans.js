/**
 * What the farmer was advised, and what they did about it.
 */

import { Router } from 'express';

import { one, query } from '../db/pool.js';
import { notFound } from '../lib/errors.js';
import { idParam, validate } from '../lib/validate.js';
import { authenticate, requireFarm, requireOwned } from './auth/middleware.js';

export const planRoutes = Router();

const date = { type: 'string', format: 'date' };

planRoutes.get(
  '/farms/:id/tasks',
  authenticate,
  validate({
    params: idParam,
    query: {
      type: 'object',
      properties: { from: date, to: date, open: { type: 'boolean', default: true } },
    },
  }),
  requireFarm(),
  async (req, res) => {
    const { from, to, open } = req.query;
    // `open` hits the partial index of scheduled/delayed tasks only.
    const { rows } = await query(
      `SELECT id, task_plan_id, field_id, title, category, priority, status, scheduled_date,
              scheduled_start_time, duration_minutes, why_now, detail, completed_at, created_at
         FROM scheduled_tasks
        WHERE farm_id = $1
          AND ($2::date IS NULL OR scheduled_date >= $2)
          AND ($3::date IS NULL OR scheduled_date <= $3)
          AND (NOT $4 OR status IN ('scheduled', 'delayed'))
        ORDER BY scheduled_date NULLS LAST, scheduled_start_time NULLS LAST
        LIMIT 200`,
      [req.params.id, from ?? null, to ?? null, open],
    );
    res.json({ items: rows });
  },
);

planRoutes.patch(
  '/tasks/:id',
  authenticate,
  validate({
    params: idParam,
    body: {
      type: 'object',
      properties: {
        status: { enum: ['scheduled', 'delayed', 'skipped', 'done', 'cancelled'] },
        scheduled_date: date,
      },
      minProperties: 1,
    },
  }),
  requireOwned('scheduled_tasks'),
  async (req, res) => {
    const { status = null, scheduled_date = null } = req.body;
    const task = await one(
      `UPDATE scheduled_tasks SET
          status = COALESCE($2, status),
          scheduled_date = COALESCE($3, scheduled_date),
          completed_at = CASE WHEN $2 = 'done' THEN COALESCE(completed_at, now())
                              WHEN $2 IS NULL THEN completed_at ELSE NULL END
        WHERE id = $1
        RETURNING id, status, scheduled_date, completed_at, updated_at`,
      [req.params.id, status, scheduled_date],
    );
    if (!task) throw notFound('Task');
    res.json(task);
  },
);

planRoutes.get('/farms/:id/irrigation-plans', authenticate, validate({ params: idParam }), requireFarm(), async (req, res) => {
  const { rows } = await query(
    `SELECT id, field_id, plan_date, crop, growth_stage, decision,
            water_depth_mm::float8 AS water_depth_mm, duration_hours::float8 AS duration_hours,
            method, status, applied_at, applied_depth_mm::float8 AS applied_depth_mm, plan, created_at
       FROM irrigation_plans WHERE farm_id = $1
      ORDER BY plan_date DESC, created_at DESC LIMIT 60`,
    [req.params.id],
  );
  res.json({ items: rows });
});

// Recording what was actually applied closes the loop on the advice.
planRoutes.patch(
  '/irrigation-plans/:id',
  authenticate,
  validate({
    params: idParam,
    body: {
      type: 'object',
      properties: {
        status: { enum: ['applied', 'skipped'] },
        applied_depth_mm: { type: 'number', minimum: 0, maximum: 500 },
      },
      required: ['status'],
    },
  }),
  requireOwned('irrigation_plans'),
  async (req, res) => {
    const { status, applied_depth_mm = null } = req.body;
    const plan = await one(
      `UPDATE irrigation_plans SET status = $2,
              applied_at = CASE WHEN $2 = 'applied' THEN now() END,
              applied_depth_mm = CASE WHEN $2 = 'applied' THEN $3::numeric END
        WHERE id = $1
        RETURNING id, status, applied_at, applied_depth_mm::float8 AS applied_depth_mm`,
      [req.params.id, status, applied_depth_mm],
    );
    if (!plan) throw notFound('Irrigation plan');
    res.json(plan);
  },
);

planRoutes.get('/farms/:id/crop-recommendations', authenticate, validate({ params: idParam }), requireFarm(), async (req, res) => {
  const { rows } = await query(
    `SELECT id, field_id, top_crop, confidence, recommendations, season, agent_version,
            model_version, created_at
       FROM crop_recommendations WHERE farm_id = $1 ORDER BY created_at DESC LIMIT 20`,
    [req.params.id],
  );
  res.json({ items: rows });
});

import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  canonicalPayload, cellKey, contentHash, cropRow, expandPayload, irrigationRows, stableStringify,
  taskPlan, toDate, unitInterval,
} from '../src/modules/chat/canonical.js';

const schedule = {
  agent_version: '2.1.0',
  headline: 'Spray before the rain',
  planning_horizon_days: 3,
  generated_at: '2026-09-23T04:00:00Z',
  all_tasks: [
    { title: 'Spray', priority: 'critical', scheduled_date: '2026-09-23', scheduled_start_time: '07:00', do: ['mix'] },
    { title: 'Weed', priority: 'medium', scheduled_date: '2026-09-23', scheduled_start_time: '06:00' },
    { title: 'Scout', priority: 'low', delay_until_date: '2026-09-25' },
  ],
};

test('task plan: derived views are dropped on write and rebuilt identically on read', () => {
  const full = expandPayload('task_scheduler', schedule);
  const stored = canonicalPayload('task_scheduler', full);
  assert.equal(stored.daily_plans, undefined);
  assert.equal(stored.critical_tasks, undefined);
  assert.deepEqual(expandPayload('task_scheduler', stored), full);

  assert.deepEqual(full.critical_tasks.map((t) => t.title), ['Spray']);
  assert.deepEqual(full.daily_plans.map((d) => d.plan_date), ['2026-09-23', '2026-09-25']);
  assert.deepEqual(full.daily_plans[0].tasks.map((t) => t.title), ['Weed', 'Spray'], 'sorted by start time');
  assert.equal(full.daily_plans[0].critical_tasks, 1);
});

test('other agents are stored untouched', () => {
  const payload = { daily_plans: [1] };
  assert.equal(canonicalPayload('irrigation_planner', payload), payload);
  assert.equal(expandPayload('irrigation_planner', payload), payload);
});

test('content hash ignores key order but not values', () => {
  assert.equal(stableStringify({ b: 1, a: { d: [1, 2], c: null } }), '{"a":{"c":null,"d":[1,2]},"b":1}');
  assert.equal(contentHash({ a: 1, b: 2 }), contentHash({ b: 2, a: 1 }));
  assert.notEqual(contentHash({ a: 1 }), contentHash({ a: 2 }));
});

test('weather cell is the cache cell: 2 decimal places', () => {
  assert.equal(cellKey({ lat: 21.17024, lon: 72.83106 }), '21.17,72.83');
  assert.equal(cellKey({ lat: 21.174, lon: 72.834 }), cellKey({ lat: 21.166, lon: 72.826 }));
  assert.equal(cellKey(null), null);
  assert.equal(cellKey({ lat: 1 }), null);
});

test('confidence accepts fractions and percentages, rejects nonsense', () => {
  assert.equal(unitInterval(0.8), 0.8);
  assert.equal(unitInterval(80), 0.8);
  assert.equal(unitInterval(-1), null);
  assert.equal(unitInterval(250), null);
  assert.equal(unitInterval(null), null);
  assert.equal(unitInterval('x'), null);
});

test('dates', () => {
  assert.equal(toDate('2026-09-23T10:00:00Z'), '2026-09-23');
  assert.equal(toDate('23/09/2026'), null);
  assert.equal(toDate(null), null);
});

test('task rows: unknown priority and status fall back, bad times dropped', () => {
  const plan = taskPlan({
    all_tasks: [
      { title: 'A', priority: 'urgent!', status: 'weird', scheduled_start_time: '7am', duration_minutes: 0 },
      { title: '' },
      'not a task',
    ],
  });
  assert.equal(plan.tasks.length, 1);
  assert.deepEqual(
    [plan.tasks[0].priority, plan.tasks[0].status, plan.tasks[0].scheduled_start_time, plan.tasks[0].duration_minutes],
    ['medium', 'scheduled', null, 60],
  );
  assert.equal(plan.plan.all_tasks, undefined, 'tasks live as rows, not in the header');
  assert.equal(taskPlan({ headline: 'no tasks key' }), null);
});

test('irrigation rows: impossible depth dropped, day kept', () => {
  const rows = irrigationRows({
    crop: 'wheat',
    irrigation_schedule: [
      { date: '2026-09-23', irrigation_required: true, water_depth_mm: 9000 },
      { date: 'soon' },
      { date: '2026-09-24', decision_code: 'SKIP_RAIN', water_depth_mm: 0 },
    ],
  });
  assert.deepEqual(rows.map((r) => [r.plan_date, r.decision, r.water_depth_mm]), [
    ['2026-09-23', 'IRRIGATE', null],
    ['2026-09-24', 'SKIP_RAIN', 0],
  ]);
});

test('crop row reads the nested result block', () => {
  const row = cropRow({ agent_version: '3', result: { season: 'rabi', recommendations: [{ crop: 'wheat', confidence: 91 }] } });
  assert.deepEqual([row.top_crop, row.confidence, row.season], ['wheat', 0.91, 'rabi']);
  assert.equal(cropRow({ result: { recommendations: [] } }), null);
});

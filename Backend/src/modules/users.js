import { Router } from 'express';

import { one, query } from '../db/pool.js';
import { HttpError, notFound } from '../lib/errors.js';
import { idParam, validate } from '../lib/validate.js';
import { STAFF, authenticate } from './auth/middleware.js';

// Accounts are created by /auth/register and edited by PATCH /auth/me.
export const userRoutes = Router();

const COLUMNS = 'id, name, email, phone, language, role, onboarded_at, created_at, updated_at';

/** Your own account, or any account for staff. */
function selfOrStaff(req, res, next) {
  if (req.user.id === req.params.id || STAFF.has(req.user.role)) return next();
  return next(notFound('User'));
}

userRoutes.get('/users/:id', authenticate, validate({ params: idParam }), selfOrStaff, async (req, res) => {
  const user = await one(`SELECT ${COLUMNS} FROM users WHERE id = $1 AND deleted_at IS NULL`, [req.params.id]);
  if (!user) throw notFound('User');
  res.json(user);
});

// Erasure (DPDP Act right to erasure): a real delete, by the account owner or
// a super admin. Farms, fields, readings, plans and conversations cascade; run
// metadata keeps no personal data and only loses its farm link. Archived
// partitions are handled by the archive's own retention, which the privacy
// notice must state.
userRoutes.delete('/users/:id', authenticate, validate({ params: idParam }), async (req, res) => {
  if (req.user.id !== req.params.id && req.user.role !== 'super_admin') {
    throw new HttpError(403, 'forbidden', 'Only the account owner can delete this account.');
  }
  const { rowCount } = await query('DELETE FROM users WHERE id = $1', [req.params.id]);
  if (!rowCount) throw notFound('User');
  res.status(204).end();
});

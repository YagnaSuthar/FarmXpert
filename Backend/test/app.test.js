// Route wiring on an ephemeral port, with no database and no AI backend.
process.env.ADMIN_API_KEY = 'test-admin-key-123';
process.env.AI_BACKEND_URL = 'http://127.0.0.1:9';

const assert = (await import('node:assert/strict')).default;
const { after, before, test } = await import('node:test');
const { createApp } = await import('../src/app.js');

let server;
let base;

before(async () => {
  server = createApp().listen(0);
  await new Promise((r) => server.once('listening', r));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(() => new Promise((r) => server.close(r)));

const call = (path, init = {}) => fetch(`${base}${path}`, {
  ...init,
  headers: { 'content-type': 'application/json', ...(init.headers || {}) },
});

test('liveness never touches dependencies', async () => {
  const res = await call('/health');
  assert.equal(res.status, 200);
  assert.equal((await res.json()).status, 'ok');
  assert.ok(res.headers.get('x-request-id'));
  assert.equal(res.headers.get('x-powered-by'), null);
});

test('readiness reports a missing database as not ready', async () => {
  const res = await call('/ready');
  assert.equal(res.status, 503);
  assert.equal((await res.json()).database, 'not_configured');
});

test('unknown routes and bad JSON get the standard error shape', async () => {
  assert.equal((await call('/api/v1/nope')).status, 404);
  const res = await call('/api/v1/chat/ask', { method: 'POST', body: '{"query":' });
  assert.equal(res.status, 400);
  assert.equal((await res.json()).error.code, 'bad_request');
});

test('every farmer route refuses a caller without a valid token', async () => {
  const routes = [
    ['POST', '/api/v1/chat/ask'], ['GET', '/api/v1/conversations'], ['GET', '/api/v1/farms'],
    ['POST', '/api/v1/farms'], ['GET', '/api/v1/farms/3f2b8c1e-7d4a-4e9b-9c1a-2b3c4d5e6f70'],
    ['POST', '/api/v1/onboarding'], ['GET', '/api/v1/auth/me'], ['POST', '/api/v1/voice/ask'],
    ['PATCH', '/api/v1/tasks/3f2b8c1e-7d4a-4e9b-9c1a-2b3c4d5e6f70'],
  ];
  for (const [method, path] of routes) {
    const res = await call(path, { method, body: method === 'GET' ? undefined : '{}' });
    assert.equal(res.status, 401, `${method} ${path}`);
    assert.equal((await res.json()).error.code, 'auth_required');
  }
  const forged = await call('/api/v1/farms', { headers: { authorization: 'Bearer not.a.token' } });
  assert.equal(forged.status, 401);
  assert.equal((await forged.json()).error.code, 'token_invalid');
});

test('public auth routes validate before touching the database', async () => {
  const res = await call('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ email: 'not-an-email', password: 'x' }) });
  assert.equal(res.status, 422);
  const code = await call('/api/v1/auth/verify-email', { method: 'POST', body: JSON.stringify({ email: 'a@b.co', code: '12ab' }) });
  assert.equal(code.status, 422);
});

test('market prices stay public: the AI backend reads them without an account', async () => {
  const res = await call('/api/v1/market/prices');
  assert.equal(res.status, 422, 'validation (commodity required), not 401');
});

test('admin routes require the admin key', async () => {
  assert.equal((await call('/api/v1/admin/archive')).status, 401);
  assert.equal((await call('/api/v1/admin/archive', { headers: { 'x-admin-key': 'wrong-key-of-same-len' } })).status, 401);
  // Usage reports live in their own module; they must be guarded all the same.
  assert.equal((await call('/api/v1/admin/usage')).status, 401);
  const limit = await call('/api/v1/admin/users/3f2b8c1e-7d4a-4e9b-9c1a-2b3c4d5e6f70/token-limit',
    { method: 'PUT', body: JSON.stringify({ limit: 10 }) });
  assert.equal(limit.status, 401);
});

test('the request id is echoed when the client supplies a sane one', async () => {
  const res = await call('/health', { headers: { 'x-request-id': 'client-req-0001' } });
  assert.equal(res.headers.get('x-request-id'), 'client-req-0001');
  const bad = await call('/health', { headers: { 'x-request-id': 'bad id!' } });
  assert.notEqual(bad.headers.get('x-request-id'), 'bad id!');
});

test('bursts are rate limited per user, with Retry-After', async () => {
  const { rateLimit } = await import('../src/lib/rateLimit.js');
  const limiter = rateLimit({ perMinute: 2, name: 'test' });
  const results = [];
  const res = { headers: {}, set(k, v) { this.headers[k] = v; } };
  for (let i = 0; i < 3; i += 1) {
    limiter({ user: { id: 'u1' }, body: {}, query: {}, ip: '1.1.1.1' }, res, (err) => results.push(err?.status ?? 200));
  }
  limiter({ user: { id: 'u2' }, body: {}, query: {}, ip: '1.1.1.1' }, res, (err) => results.push(err?.status ?? 200));
  // A user id in the body is not an identity: it cannot buy a fresh allowance.
  limiter({ body: { user_id: 'u3' }, query: {}, ip: '9.9.9.9' }, res, () => {});
  limiter({ body: { user_id: 'u4' }, query: {}, ip: '9.9.9.9' }, res, () => {});
  limiter({ body: { user_id: 'u5' }, query: {}, ip: '9.9.9.9' }, res, (err) => results.push(err?.status ?? 200));
  assert.deepEqual(results, [200, 200, 429, 200, 429], 'another farmer on the same network is not blocked');
  assert.ok(Number(res.headers['Retry-After']) >= 1);
});

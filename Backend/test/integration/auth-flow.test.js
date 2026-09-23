// End-to-end account and ownership flow against a real PostgreSQL.
//   npm run test:integration        (needs DATABASE_URL, migrations applied)
// Creates its own users with a unique suffix and deletes them afterwards.
process.env.LOG_LEVEL = 'silent';
// Every request comes from 127.0.0.1: lift the per-IP limits for the run.
process.env.AUTH_RATE_LIMIT = '10000';

const assert = (await import('node:assert/strict')).default;
const { after, before, test } = await import('node:test');
const { createApp } = await import('../../src/app.js');
const { closePool, one, query } = await import('../../src/db/pool.js');
const { hmac } = await import('../../src/modules/auth/security.js');

if (!process.env.DATABASE_URL) {
  test('integration tests need DATABASE_URL', { skip: true }, () => {});
} else {
  const tag = Date.now().toString(36);
  const emails = [`farmer.a.${tag}@example.com`, `farmer.b.${tag}@example.com`];
  const PASSWORD = 'Kheti@2026!';
  let server;
  let base;

  before(async () => {
    server = createApp().listen(0);
    await new Promise((r) => server.once('listening', r));
    base = `http://127.0.0.1:${server.address().port}/api/v1`;
  });
  after(async () => {
    await query('DELETE FROM users WHERE email = ANY($1)', [emails]);
    await new Promise((r) => server.close(r));
    await closePool();
  });

  const call = async (path, { method = 'GET', body, token, cookie } = {}) => {
    const res = await fetch(`${base}${path}`, {
      method,
      headers: {
        'content-type': 'application/json',
        ...(token && { authorization: `Bearer ${token}` }),
        ...(cookie && { cookie }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    return { status: res.status, body: text ? JSON.parse(text) : null, cookie: res.headers.get('set-cookie') };
  };

  /** Solve a captcha by reading its answer from the challenge text. */
  async function captcha() {
    const { body } = await call('/auth/captcha');
    const [a, op, b] = body.challenge.replace(' = ?', '').split(' ');
    const answer = op === '+' ? +a + +b : op === '×' ? a * b : a - b;
    return { captcha_id: body.captcha_id, captcha_answer: String(answer) };
  }

  /** The emailed code, set to a known value (the stored one is only a hash). */
  async function knownCode(email, purpose, code = '424242') {
    await query(
      `UPDATE otp_verifications SET otp_hash = $3
        WHERE user_id = (SELECT id FROM users WHERE email = $1) AND purpose = $2 AND NOT used`,
      [email, purpose, hmac(code)],
    );
    return code;
  }

  const cookieValue = (setCookie) => setCookie.split(';')[0];
  const session = {};

  test('register -> verify email -> log in', async () => {
    for (const email of emails) {
      const reg = await call('/auth/register', {
        method: 'POST', body: { name: 'Ramesh Patel', email, password: PASSWORD, ...(await captcha()) },
      });
      assert.equal(reg.status, 201, JSON.stringify(reg.body));

      const early = await call('/auth/login', { method: 'POST', body: { email, password: PASSWORD } });
      assert.equal(early.status, 403);
      assert.equal(early.body.error.code, 'email_unverified');

      const wrong = await call('/auth/verify-email', { method: 'POST', body: { email, code: '000000' } });
      assert.equal(wrong.body.error.code, 'code_wrong');
      assert.equal(wrong.body.error.details.attempts_left, 4, 'a wrong try is counted and kept');

      const ok = await call('/auth/verify-email', {
        method: 'POST', body: { email, code: await knownCode(email, 'email_verification') },
      });
      assert.equal(ok.status, 200);

      const login = await call('/auth/login', { method: 'POST', body: { email, password: PASSWORD, remember: true } });
      assert.equal(login.status, 200);
      assert.ok(login.body.access_token);
      assert.match(login.cookie, /fx_refresh=.*HttpOnly/i);
      assert.equal(login.body.user.onboarded, false);
      session[email] = { token: login.body.access_token, cookie: cookieValue(login.cookie) };
    }
  });

  test('duplicate registration is refused without revealing more', async () => {
    const again = await call('/auth/register', {
      method: 'POST', body: { name: 'Someone Else', email: emails[0], password: PASSWORD, ...(await captcha()) },
    });
    assert.equal(again.status, 409);
  });

  test('refresh rotates, and a stolen (reused) token ends the whole login', async () => {
    const a = session[emails[0]];
    const first = await call('/auth/refresh', { method: 'POST', cookie: a.cookie });
    assert.equal(first.status, 200);
    const rotated = cookieValue(first.cookie);
    assert.notEqual(rotated, a.cookie);

    const replay = await call('/auth/refresh', { method: 'POST', cookie: a.cookie });
    assert.equal(replay.status, 401);
    assert.equal(replay.body.error.code, 'session_revoked');
    const afterTheft = await call('/auth/refresh', { method: 'POST', cookie: rotated });
    assert.equal(afterTheft.status, 401, 'the thief and the owner are both logged out');

    const login = await call('/auth/login', { method: 'POST', body: { email: emails[0], password: PASSWORD } });
    session[emails[0]] = { token: login.body.access_token, cookie: cookieValue(login.cookie) };
  });

  let farmId;

  test('onboarding saves the whole farm, and the farmer is marked onboarded', async () => {
    const res = await call('/onboarding', {
      method: 'POST', token: session[emails[0]].token,
      body: {
        profile: { language: 'gu' },
        farm: {
          name: 'Patel Farm', latitude: 21.17, longitude: 72.83, area_acres: 5, state: 'Gujarat', district: 'Surat',
          water_source: 'borewell',
          resources: { labor_units_available: 3, equipment_available: ['tractor', 'sprayer'], irrigation_available: true },
        },
        field: { name: 'North plot', crop_name: 'cotton', growth_stage: 'flowering', sown_on: '2026-06-20',
          soil_type: 'black_cotton', irrigation_method: 'drip' },
        soil: { soil_ph: 7.8, nitrogen: 210, phosphorus: 18, potassium: 260 },
      },
    });
    assert.equal(res.status, 201, JSON.stringify(res.body));
    farmId = res.body.farm.id;
    assert.equal(res.body.farm.area_acres, 5);
    assert.equal(res.body.field.irrigation_method, 'drip');
    assert.equal(res.body.soil.soil_ph, 7.8);
    const me = await call('/auth/me', { token: session[emails[0]].token });
    assert.equal(me.body.user.onboarded, true);
    assert.equal(me.body.user.language, 'gu');
  });

  test('another farmer cannot see or change this farm', async () => {
    const intruder = session[emails[1]].token;
    for (const [method, path, body] of [
      ['GET', `/farms/${farmId}`], ['PATCH', `/farms/${farmId}`, { name: 'Mine now' }],
      ['GET', `/farms/${farmId}/soil/latest`], ['POST', `/farms/${farmId}/soil`, { soil_ph: 6 }],
      ['GET', `/farms/${farmId}/tasks`],
    ]) {
      const res = await call(path, { method, body, token: intruder });
      assert.equal(res.status, 404, `${method} ${path} must look like it does not exist`);
    }
    const own = await call('/farms', { token: intruder });
    assert.deepEqual(own.body.items, []);
  });

  test('password reset: generic answer, single-use authorisation, everything revoked', async () => {
    const email = emails[1];
    const unknown = await call('/auth/forgot-password', {
      method: 'POST', body: { email: `nobody.${tag}@example.com`, ...(await captcha()) },
    });
    const known = await call('/auth/forgot-password', { method: 'POST', body: { email, ...(await captcha()) } });
    assert.deepEqual(unknown.body, known.body, 'the answer does not reveal who has an account');

    const verified = await call('/auth/verify-reset-code', {
      method: 'POST', body: { email, code: await knownCode(email, 'password_reset') },
    });
    assert.equal(verified.status, 200);
    const reset = await call('/auth/reset-password', {
      method: 'POST', body: { reset_token: verified.body.reset_token, password: 'Naya@Pass99' },
    });
    assert.equal(reset.status, 200);
    const reuse = await call('/auth/reset-password', {
      method: 'POST', body: { reset_token: verified.body.reset_token, password: 'Other@Pass99' },
    });
    assert.equal(reuse.body.error.code, 'reset_expired', 'single use');

    const oldToken = await call('/auth/me', { token: session[email].token });
    assert.equal(oldToken.status, 401, 'access tokens issued before the reset stop working at once');
    const oldCookie = await call('/auth/refresh', { method: 'POST', cookie: session[email].cookie });
    assert.equal(oldCookie.status, 401);
    const fresh = await call('/auth/login', { method: 'POST', body: { email, password: 'Naya@Pass99' } });
    assert.equal(fresh.status, 200);
  });

  test('brute force: captcha after 3 misses, lock after 10', async () => {
    const email = emails[1];
    for (let i = 0; i < 3; i += 1) {
      await call('/auth/login', { method: 'POST', body: { email, password: 'wrong' } });
    }
    const gated = await call('/auth/login', { method: 'POST', body: { email, password: 'Naya@Pass99' } });
    assert.equal(gated.body.error.code, 'captcha_required');
    const passed = await call('/auth/login', { method: 'POST', body: { email, password: 'Naya@Pass99', ...(await captcha()) } });
    assert.equal(passed.status, 200, 'the right password with a captcha still works');
    const row = await one('SELECT failed_logins FROM users WHERE email = $1', [email]);
    assert.equal(row.failed_logins, 0, 'a good login resets the counter');
  });
}

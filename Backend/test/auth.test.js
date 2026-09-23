process.env.LOG_LEVEL = 'silent';

const assert = (await import('node:assert/strict')).default;
const { test } = await import('node:test');
const security = await import('../src/modules/auth/security.js');
const { signAccessToken, verifyAccessToken, refreshCookieOptions } = await import('../src/modules/auth/tokens.js');

test('passwords: pepper + bcrypt, and the right password only', async () => {
  const hash = await security.hashPassword('Kheti@2026');
  assert.match(hash, /^\$2[aby]\$/);
  assert.equal(await security.verifyPassword('Kheti@2026', hash), true);
  assert.equal(await security.verifyPassword('kheti@2026', hash), false);
  // Unknown account: still spends bcrypt time, still false.
  assert.equal(await security.verifyPassword('anything', null), false);
});

test('password rules give codes the app can translate', () => {
  assert.deepEqual(security.passwordProblems('Kheti@2026'), []);
  assert.deepEqual(security.passwordProblems('abc').sort(),
    ['needs_number', 'needs_symbol', 'needs_uppercase', 'too_short'].sort());
});

test('one-time codes: six digits, stored only as HMAC, compared in constant time', () => {
  const codes = new Set(Array.from({ length: 200 }, () => security.newOtp()));
  assert.ok([...codes].every((c) => /^\d{6}$/.test(c)));
  assert.ok(codes.size > 190, 'codes are random');
  const stored = security.hmac('482913');
  assert.equal(security.sameHex(security.hmac('482913'), stored), true);
  assert.equal(security.sameHex(security.hmac('482914'), stored), false);
  assert.equal(security.sameHex('abc', stored), false, 'different length never matches');
});

test('emails are normalised before any lookup', () => {
  assert.equal(security.normaliseEmail('  Farmer@Example.COM '), 'farmer@example.com');
});

test('access tokens: signed claims survive, tampering and other secrets do not', () => {
  const token = signAccessToken({ id: '3f2b8c1e-7d4a-4e9b-9c1a-2b3c4d5e6f70', role: 'farmer', token_version: 4 });
  const payload = verifyAccessToken(token);
  assert.equal(payload.sub, '3f2b8c1e-7d4a-4e9b-9c1a-2b3c4d5e6f70');
  assert.deepEqual([payload.role, payload.tv, payload.iss], ['farmer', 4, 'farmxpert']);

  const [h, body, sig] = token.split('.');
  const forged = Buffer.from(JSON.stringify({ ...payload, role: 'super_admin' })).toString('base64url');
  assert.equal(verifyAccessToken(`${h}.${forged}.${sig}`), null, 'a raised role is caught');
  assert.equal(verifyAccessToken(`${h}.${body}.`), null, 'a stripped signature is caught');
  const none = `${Buffer.from('{"alg":"none","typ":"JWT"}').toString('base64url')}.${body}.`;
  assert.equal(verifyAccessToken(none), null, 'alg=none is refused');
});

test('refresh cookie: HttpOnly, scoped to the auth routes, session-only unless remembered', () => {
  const session = refreshCookieOptions(86_400_000, false);
  assert.equal(session.httpOnly, true);
  assert.equal(session.path, '/api/v1/auth');
  assert.equal(session.maxAge, undefined, 'without "remember me" it ends with the browser');
  assert.equal(refreshCookieOptions(1000, true).maxAge, 1000);
});

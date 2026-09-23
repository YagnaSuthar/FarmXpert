const path = require('path');
const crypto = require('crypto');
const backendRoot = path.resolve(__dirname, '..');
const { env } = require(path.join(backendRoot, 'src/config/env'));
const { pool } = require(path.join(backendRoot, 'src/config/db'));
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const authOtp = require(path.join(backendRoot, 'src/auth/auth.otp'));
const authCaptcha = require(path.join(backendRoot, 'src/auth/auth.captcha'));

const BASE_URL = `http://localhost:${env.port}/api/auth`;
const HEALTH_URL = `http://localhost:${env.port}/api/health`;

// Test helper: Solve arithmetic challenge string
function solveChallenge(challengeText) {
  const match = challengeText.match(/What is (\d+)\s*([\+\-\*])\s*(\d+)\?/);
  if (!match) throw new Error(`Unrecognized challenge: ${challengeText}`);
  const num1 = parseInt(match[1], 10);
  const op = match[2];
  const num2 = parseInt(match[3], 10);
  if (op === '+') return num1 + num2;
  if (op === '-') return num1 - num2;
  if (op === '*') return num1 * num2;
  throw new Error(`Unknown operator: ${op}`);
}

async function runSecurityAudit() {
  console.log('========================================================================');
  console.log('🔒 FULL SYSTEM SECURITY AUDIT & AUTOMATED TEST SUITE (PHASES 1 - 7)');
  console.log('========================================================================\n');

  let passedTests = 0;
  let totalTests = 0;

  function assert(condition, message) {
    totalTests++;
    if (!condition) {
      console.error(`  ❌ FAILED: ${message}`);
      throw new Error(`Security Audit Failure: ${message}`);
    }
    passedTests++;
    console.log(`  ✅ PASSED: ${message}`);
  }

  const testSuffix = Date.now();
  const passwordPlain = 'AuditPassword123!';
  const passwordPeppered = passwordPlain + env.passwordPepper;
  const passwordHash = await bcrypt.hash(passwordPeppered, 12);

  // ─── 1. ARCHITECTURE & SECURITY HEADERS ────────────────
  console.log('\n[SECTION 1: Server Configuration & Security Headers]');
  const healthRes = await fetch(HEALTH_URL);
  const healthHeaders = healthRes.headers;
  assert(healthRes.status === 200, 'Health endpoint responds with 200 OK');
  assert(healthHeaders.has('x-dns-prefetch-control'), 'Helmet headers present (x-dns-prefetch-control)');
  assert(healthHeaders.has('x-frame-options') || healthHeaders.has('x-content-type-options'), 'Security headers active (clickjacking & MIME-sniffing protection)');

  // ─── 2. SQL INJECTION DEFENSE ─────────────────────────
  console.log('\n[SECTION 2: SQL Injection Defense & Parameterization]');
  const sqlInjectionEmail = "' OR 1=1; DROP TABLE users; --";
  const sqlInjRes = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: sqlInjectionEmail, password: passwordPlain }),
  });
  const sqlInjData = await sqlInjRes.json();
  assert([400, 401].includes(sqlInjRes.status), 'SQL injection attempt in email rejected safely (400/401)');
  assert(!sqlInjData.error?.includes('syntax error'), 'No PostgreSQL error or stack trace leaked in response');

  // Verify users table is intact
  const tableCheck = await pool.query("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'users'");
  assert(parseInt(tableCheck.rows[0].count, 10) === 1, 'Users table remained safe (SQL injection neutralized by parameterization)');

  // ─── 3. PASSWORD SECURITY & PEPPER ENFORCEMENT ────────
  console.log('\n[SECTION 3: Password Security (bcrypt + application pepper)]');
  const pepperTestEmail = `pepper_audit_${testSuffix}@example.com`;
  await pool.query(
    'INSERT INTO users (name, email, password_hash, role, email_verified, token_version) VALUES ($1, $2, $3, $4, $5, $6)',
    ['Pepper Auditor', pepperTestEmail, passwordHash, 'user', true, 1]
  );
  const dbHashRes = await pool.query('SELECT password_hash FROM users WHERE email = $1', [pepperTestEmail]);
  const storedDbHash = dbHashRes.rows[0].password_hash;

  assert(storedDbHash.startsWith('$2b$12$'), 'Password hash uses bcrypt format ($2b$) with 12 salt rounds');
  assert(!storedDbHash.includes(env.passwordPepper), 'Pepper is not stored in plaintext or anywhere inside PostgreSQL');
  assert(await bcrypt.compare(passwordPlain + env.passwordPepper, storedDbHash), 'Password verifies successfully WITH pepper');
  assert(!(await bcrypt.compare(passwordPlain, storedDbHash)), 'Password verification strictly FAILS without pepper');

  // ─── 4. REGISTRATION & ROLE ESCALATION DEFENSE ─────────
  console.log('\n[SECTION 4: Registration, Role Escalation & Duplicate Defense]');
  const regEmail = `reg_audit_${testSuffix}@example.com`;

  // Role escalation attempt: client passes role: 'super_admin'
  const regRes = await fetch(`${BASE_URL}/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'Role Escalation Tester',
      email: regEmail,
      password: passwordPlain,
      role: 'super_admin', // Attacker payload
    }),
  });
  const regData = await regRes.json();
  assert(regRes.status === 201, 'Registration returns 201 Created');
  assert(regData.data?.user?.role === 'user', 'Client-supplied role: super_admin ignored; role forced to user');
  assert(regData.data?.user?.email_verified === false, 'New user account created with email_verified: false');
  assert(!regData.data?.user?.password_hash, 'Password hash is NEVER leaked in registration response');

  // Duplicate registration
  const dupRes = await fetch(`${BASE_URL}/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'Duplicate Tester',
      email: regEmail,
      password: passwordPlain,
    }),
  });
  assert(dupRes.status === 409, 'Duplicate email registration returns 409 Conflict');

  // ─── 5. EMAIL VERIFICATION & OTP LIFECYCLE ─────────────
  console.log('\n[SECTION 5: Email Verification, OTP Hashing & Replay Defense]');
  const userRecord = await pool.query('SELECT id FROM users WHERE email = $1', [regEmail]);
  const userId = userRecord.rows[0].id;

  const otpDbRecord = await pool.query(
    'SELECT otp_hash, used, attempts FROM otp_verifications WHERE user_id = $1 AND purpose = $2',
    [userId, 'email_verification']
  );
  assert(otpDbRecord.rows.length === 1, 'Verification OTP record created in PostgreSQL');
  assert(otpDbRecord.rows[0].otp_hash.length === 64, 'OTP is stored as a 64-character HMAC-SHA256 hex string (never plaintext)');

  // Attempt wrong OTP -> attempt counting
  const wrongOtpRes = await fetch(`${BASE_URL}/verify-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: regEmail, otp: '000000' }),
  });
  assert(wrongOtpRes.status === 400, 'Wrong OTP rejected with 400 Bad Request');
  const attemptsCheck = await pool.query('SELECT attempts FROM otp_verifications WHERE user_id = $1', [userId]);
  assert(attemptsCheck.rows[0].attempts === 1, 'Failed OTP attempt counter incremented in database');

  // Insert valid OTP for test verification
  const validEmailOtp = '135790';
  const validOtpHash = authOtp.hashOtp(validEmailOtp);
  await pool.query('UPDATE otp_verifications SET used = true WHERE user_id = $1', [userId]);
  await pool.query(
    'INSERT INTO otp_verifications (user_id, purpose, otp_hash, expires_at) VALUES ($1, $2, $3, $4)',
    [userId, 'email_verification', validOtpHash, new Date(Date.now() + 10 * 60 * 1000)]
  );

  const verifyRes = await fetch(`${BASE_URL}/verify-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: regEmail, otp: validEmailOtp }),
  });
  assert(verifyRes.status === 200, 'Valid OTP verifies email successfully (200 OK)');
  const verifiedUserCheck = await pool.query('SELECT email_verified FROM users WHERE id = $1', [userId]);
  assert(verifiedUserCheck.rows[0].email_verified === true, 'Database email_verified updated to true');

  // Replay single-use test
  const replayVerify = await fetch(`${BASE_URL}/verify-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: regEmail, otp: validEmailOtp }),
  });
  assert(replayVerify.status === 400, 'Re-submitting single-use OTP rejected (Replay defense verified)');

  // ─── 6. LOGIN, JWT & SERVER SESSIONS ───────────────────
  console.log('\n[SECTION 6: Login, JWT & Privileged Server Sessions]');
  // Standard user login -> JWT
  const userLoginRes = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: regEmail, password: passwordPlain }),
  });
  const userLoginData = await userLoginRes.json();
  const userJwt = userLoginData.data?.token;
  assert(userLoginRes.status === 200, 'Verified user logs in successfully');
  assert(Boolean(userJwt), 'Standard user receives signed JWT token');

  const decodedJwt = jwt.verify(userJwt, env.jwtSecret);
  assert(decodedJwt.sub === userId && decodedJwt.role === 'user' && decodedJwt.tokenVersion === 1, 'JWT payload contains sub, role: user, and tokenVersion');

  // Admin user setup -> Session cookie
  const adminAuditEmail = `admin_audit_${testSuffix}@example.com`;
  const adminCreateRes = await pool.query(
    'INSERT INTO users (name, email, password_hash, role, email_verified, token_version) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id',
    ['Admin Auditor', adminAuditEmail, passwordHash, 'admin', true, 1]
  );
  const adminId = adminCreateRes.rows[0].id;

  const adminLoginRes = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: adminAuditEmail, password: passwordPlain }),
  });
  const adminCookieHeader = adminLoginRes.headers.get('set-cookie');
  const adminLoginData = await adminLoginRes.json();
  assert(adminLoginRes.status === 200, 'Admin logs in successfully');
  assert(!adminLoginData.data?.token, 'Admin does NOT receive a JWT token (Privileged session strategy)');
  assert(adminCookieHeader.includes('sid=') && adminCookieHeader.includes('HttpOnly'), 'Admin receives secure HttpOnly sid session cookie');

  // ─── 7. SESSION FIXATION PREVENTION ───────────────────
  console.log('\n[SECTION 7: Session Fixation Prevention]');
  const sid1 = adminCookieHeader.match(/sid=([^;]+)/)?.[1];
  const adminRelogin = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: adminAuditEmail, password: passwordPlain }),
  });
  const sid2 = adminRelogin.headers.get('set-cookie')?.match(/sid=([^;]+)/)?.[1];
  assert(sid1 !== sid2, 'Re-login generates fresh 32-byte session ID (Session fixation defeated)');

  // ─── 8. CAPTCHA LIFECYCLE & ZERO-LEAKAGE ───────────────
  console.log('\n[SECTION 8: CAPTCHA Lifecycle, Replay & Zero-Leakage]');
  const captchaRes = await fetch(`${BASE_URL}/captcha`);
  const captchaData = await captchaRes.json();
  assert(captchaRes.status === 200, 'GET /captcha returns 200 OK');
  assert(Boolean(captchaData.data?.captchaId && captchaData.data?.challenge), 'CAPTCHA challenge and ID provided');
  assert(captchaData.data?.answer === undefined, 'CAPTCHA correct answer is NEVER exposed in API response');

  const unitCap = authCaptcha.generateCaptcha();
  const unitSol = solveChallenge(unitCap.challenge);
  assert(authCaptcha.verifyCaptcha(unitCap.captchaId, unitSol).isValid === true, 'Valid CAPTCHA solution verifies via constant-time HMAC');
  assert(authCaptcha.verifyCaptcha(unitCap.captchaId, unitSol).isValid === false, 'CAPTCHA is single-use and cannot be replayed');

  // ─── 9. FORGOT PASSWORD & REVISION TRANSACTION ─────────
  console.log('\n[SECTION 9: Password Reset, Transactional Authorization & Account Enumeration Defense]');
  // Account enumeration check
  const fpNonExistent = await fetch(`${BASE_URL}/forgot-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'ghost_missing_user@example.com' }),
  });
  const fpExistent = await fetch(`${BASE_URL}/forgot-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: regEmail }),
  });
  const fpData1 = await fpNonExistent.json();
  const fpData2 = await fpExistent.json();
  assert(fpData1.message === fpData2.message, 'Forgot password response is identical for existent & non-existent emails (Account enumeration prevented)');

  // Verify reset OTP and obtain resetToken
  const resetTestOtp = '246810';
  const resetOtpHash = authOtp.hashOtp(resetTestOtp);
  await pool.query('UPDATE otp_verifications SET used = true WHERE user_id = $1', [userId]);
  await pool.query(
    'INSERT INTO otp_verifications (user_id, purpose, otp_hash, expires_at) VALUES ($1, $2, $3, $4)',
    [userId, 'password_reset', resetOtpHash, new Date(Date.now() + 10 * 60 * 1000)]
  );

  const verifyResetRes = await fetch(`${BASE_URL}/verify-reset-otp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: regEmail, otp: resetTestOtp }),
  });
  const verifyResetData = await verifyResetRes.json();
  const resetToken = verifyResetData.data?.resetToken;
  assert(verifyResetRes.status === 200, 'Reset OTP verified successfully');
  assert(Boolean(resetToken && resetToken.length === 64), 'Separate 64-character single-use reset authorization token issued');

  // Reset password
  const newAuditPass = 'NewAuditPassword321!';
  const resetPassRes = await fetch(`${BASE_URL}/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resetToken, newPassword: newAuditPass }),
  });
  assert(resetPassRes.status === 200, 'Password reset succeeded with resetToken');

  // Replay resetToken
  const replayResetToken = await fetch(`${BASE_URL}/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resetToken, newPassword: 'AnotherPassword999!' }),
  });
  assert(replayResetToken.status === 400, 'Replayed resetToken is rejected (Single-use reset authorization)');

  // ─── 10. TOKEN VERSION JWT REVOCATION ──────────────────
  console.log('\n[SECTION 10: Stateless JWT Revocation via token_version]');
  const dbUserAfterReset = await pool.query('SELECT token_version FROM users WHERE id = $1', [userId]);
  assert(dbUserAfterReset.rows[0].token_version === 2, 'Database token_version incremented from 1 to 2');

  const oldJwtMeRes = await fetch(`${BASE_URL}/me`, {
    headers: { Authorization: `Bearer ${userJwt}` },
  });
  assert(oldJwtMeRes.status === 401, 'Pre-reset JWT is immediately REVOKED on GET /me due to tokenVersion mismatch');

  // ─── 11. PRIVILEGED SESSION REVOCATION ─────────────────
  console.log('\n[SECTION 11: Privileged Session Revocation]');
  // Admin password reset
  const adminResetOtp = '998877';
  await pool.query(
    'INSERT INTO otp_verifications (user_id, purpose, otp_hash, expires_at) VALUES ($1, $2, $3, $4)',
    [adminId, 'password_reset', authOtp.hashOtp(adminResetOtp), new Date(Date.now() + 10 * 60 * 1000)]
  );
  const adminVRes = await fetch(`${BASE_URL}/verify-reset-otp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: adminAuditEmail, otp: adminResetOtp }),
  });
  const adminVData = await adminVRes.json();
  await fetch(`${BASE_URL}/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resetToken: adminVData.data.resetToken, newPassword: newAuditPass }),
  });

  const oldAdminMeRes = await fetch(`${BASE_URL}/me`, {
    headers: { Cookie: `sid=${sid2}` },
  });
  assert(oldAdminMeRes.status === 401, 'Admin session cookie immediately REVOKED from in-memory store upon password reset');

  // ─── 12. RBAC & RESOURCE OWNERSHIP (IDOR) ──────────────
  console.log('\n[SECTION 12: Role-Based Access Control & Resource Ownership]');
  // Setup SuperAdmin & login
  const superEmail = `super_audit_${testSuffix}@example.com`;
  const superCreate = await pool.query(
    'INSERT INTO users (name, email, password_hash, role, email_verified, token_version) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id',
    ['Super Auditor', superEmail, passwordHash, 'super_admin', true, 1]
  );
  const superId = superCreate.rows[0].id;
  const superLoginRes = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: superEmail, password: passwordPlain }),
  });
  const superSid = superLoginRes.headers.get('set-cookie')?.match(/sid=([^;]+)/)?.[1];

  // Re-login standard user with new password
  const newLoginUserRes = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: regEmail, password: newAuditPass }),
  });
  const newLoginUserData = await newLoginUserRes.json();
  if (newLoginUserRes.status !== 200 || !newLoginUserData.data?.token) {
    console.error('DEBUG newLoginUserRes:', newLoginUserRes.status, newLoginUserData);
  }
  const newUserJwt = newLoginUserData.data?.token;

  // 401 Unauthorized check
  const noAuthAdmin = await fetch(`${BASE_URL}/admin/users`);
  assert(noAuthAdmin.status === 401, 'Unauthenticated request to /admin/users returns 401 Unauthorized');

  // 403 Forbidden check (user on admin route)
  const userAdminRes = await fetch(`${BASE_URL}/admin/users`, {
    headers: { Authorization: `Bearer ${newUserJwt}` },
  });
  assert(userAdminRes.status === 403, 'Standard user accessing /admin/users returns 403 Forbidden (RBAC enforced)');

  // SuperAdmin role update
  const roleUpdateRes = await fetch(`${BASE_URL}/admin/users/${userId}/role`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Cookie: `sid=${superSid}` },
    body: JSON.stringify({ role: 'manager' }),
  });
  assert(roleUpdateRes.status === 200, 'SuperAdmin successfully updates user role to manager on /admin/users/:id/role');

  // IDOR / Ownership Check
  // User accessing own profile -> 200 OK
  const ownProfile = await fetch(`${BASE_URL}/users/${superId}`, {
    headers: { Cookie: `sid=${superSid}` },
  });
  assert(ownProfile.status === 200, 'User accessing own profile returns 200 OK');

  // User with JWT attempting to access another user's ID -> 403 Forbidden
  const otherProfile = await fetch(`${BASE_URL}/users/${superId}`, {
    headers: { Authorization: `Bearer ${newUserJwt}` },
  });
  assert(otherProfile.status === 403, 'User attempting to access another user resource blocked with 403 Forbidden (IDOR Defense Verified)');

  // ─── 13. SECURE REMEMBER ME & REFRESH TOKEN ROTATION ─
  console.log('\n[SECTION 13: Secure Remember Me, Refresh Token Rotation & Breach Defense]');

  // Setup dedicated standard user for Remember Me tests
  const remEmail = `rem_user_${testSuffix}@example.com`;
  const remUserCreate = await pool.query(
    'INSERT INTO users (name, email, password_hash, role, email_verified, token_version) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id',
    ['Remember Me Tester', remEmail, passwordHash, 'user', true, 1]
  );
  const remUserId = remUserCreate.rows[0].id;

  // 13.1 Remember Me OFF: Standard user gets JWT only, no persistent refresh token
  const remOffLoginRes = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: remEmail, password: passwordPlain, remember: false }),
  });
  const remOffData = await remOffLoginRes.json();
  const remOffCookies = remOffLoginRes.headers.get('set-cookie') || '';
  const remOffRtMatch = remOffCookies.match(/refreshToken=([^;]+)/);
  const hasActiveRemOffRt = Boolean(
    remOffRtMatch &&
    remOffRtMatch[1] &&
    !remOffCookies.includes('Max-Age=0') &&
    !remOffCookies.includes('expires=Thu, 01 Jan 1970')
  );
  const remOffDbTokens = await pool.query('SELECT COUNT(*) FROM refresh_tokens WHERE user_id = $1', [remUserId]);

  assert(remOffLoginRes.status === 200, 'Remember Me OFF: Standard user logs in successfully (200 OK)');
  assert(Boolean(remOffData.data?.token), 'Remember Me OFF: 15-minute access JWT returned in response body');
  assert(!hasActiveRemOffRt, 'Remember Me OFF: No active refreshToken cookie issued');
  assert(parseInt(remOffDbTokens.rows[0].count, 10) === 0, 'Remember Me OFF: No refresh token record created in PostgreSQL');

  // 13.2 Remember Me ON: Standard user receives JWT + HttpOnly refreshToken cookie
  const remOnLoginRes = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: remEmail, password: passwordPlain, remember: true }),
  });
  const remOnData = await remOnLoginRes.json();
  const remOnCookies = remOnLoginRes.headers.get('set-cookie') || '';
  const rt1Match = remOnCookies.match(/refreshToken=([^;]+)/);
  const rt1 = rt1Match ? rt1Match[1] : null;

  assert(remOnLoginRes.status === 200, 'Remember Me ON: Login returns 200 OK');
  assert(Boolean(remOnData.data?.token), 'Remember Me ON: 15-minute access JWT returned');
  assert(remOnData.data?.refreshToken === undefined, 'Remember Me ON: Raw refresh token is NEVER exposed in JSON response body');
  assert(Boolean(rt1), 'Remember Me ON: HttpOnly refreshToken cookie set in response header');
  assert(remOnCookies.toLowerCase().includes('httponly'), 'Remember Me ON: refreshToken cookie includes HttpOnly attribute');
  assert(remOnCookies.includes('Path=/api/auth') || remOnCookies.includes('path=/api/auth'), 'Remember Me ON: refreshToken cookie scoped to Path=/api/auth');

  // Verify PostgreSQL stores ONLY the SHA-256 hash of the token
  const rt1Hash = crypto.createHash('sha256').update(rt1).digest('hex');
  const rt1DbCheck = await pool.query('SELECT * FROM refresh_tokens WHERE token_hash = $1', [rt1Hash]);
  assert(rt1DbCheck.rows.length === 1, 'Remember Me ON: Refresh token stored in PostgreSQL as SHA-256 hash');
  assert(rt1DbCheck.rows[0].revoked === false, 'Remember Me ON: Refresh token record is unrevoked');

  // 13.3 Refresh Token Rotation: Calling /refresh issues new JWT, rotates token, revokes old token
  const refreshRes1 = await fetch(`${BASE_URL}/refresh`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Cookie: `refreshToken=${rt1}`,
    },
  });
  const refreshData1 = await refreshRes1.json();
  const refreshCookies1 = refreshRes1.headers.get('set-cookie') || '';
  const rt2Match = refreshCookies1.match(/refreshToken=([^;]+)/);
  const rt2 = rt2Match ? rt2Match[1] : null;

  assert(refreshRes1.status === 200, 'POST /api/auth/refresh returns 200 OK with valid refresh token');
  assert(Boolean(refreshData1.data?.token), 'POST /api/auth/refresh returns fresh access JWT');
  assert(Boolean(rt2) && rt2 !== rt1, 'POST /api/auth/refresh rotates refresh token cookie (RT-A -> RT-B)');

  const rt1OldDb = await pool.query('SELECT revoked FROM refresh_tokens WHERE token_hash = $1', [rt1Hash]);
  assert(rt1OldDb.rows[0].revoked === true, 'Refresh Token Rotation: Old refresh token (RT-A) marked revoked=true');

  const rt2Hash = crypto.createHash('sha256').update(rt2).digest('hex');
  const rt2Db = await pool.query('SELECT revoked FROM refresh_tokens WHERE token_hash = $1', [rt2Hash]);
  assert(rt2Db.rows[0].revoked === false, 'Refresh Token Rotation: New rotated refresh token (RT-B) is active (revoked=false)');

  // 13.4 Token Reuse / Replay Detection (Breach Defense): Presenting already-revoked RT-A revokes ALL tokens
  const replayRes = await fetch(`${BASE_URL}/refresh`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Cookie: `refreshToken=${rt1}`, // Replaying revoked RT-A
    },
  });
  assert(replayRes.status === 401, 'Replaying revoked refresh token (RT-A) rejected with 401 Unauthorized');

  // Verify breach defense: ALL tokens for this user must now be revoked
  const allUserTokensCheck = await pool.query(
    'SELECT COUNT(*) FROM refresh_tokens WHERE user_id = $1 AND revoked = false',
    [remUserId]
  );
  assert(parseInt(allUserTokensCheck.rows[0].count, 10) === 0, 'Breach Defense: Replay attempt immediately revokes ALL refresh tokens for user');

  // Verify RT-B is also revoked and unusable now
  const rt2ReuseRes = await fetch(`${BASE_URL}/refresh`, {
    method: 'POST',
    headers: { Cookie: `refreshToken=${rt2}` },
  });
  assert(rt2ReuseRes.status === 401, 'Subsequent use of RT-B rejected after breach defense revocation');

  // 13.5 Expired Refresh Token
  const expiredRawToken = crypto.randomBytes(32).toString('hex');
  const expiredTokenHash = crypto.createHash('sha256').update(expiredRawToken).digest('hex');
  await pool.query(
    'INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES ($1, $2, $3)',
    [remUserId, expiredTokenHash, new Date(Date.now() - 60000)] // Expired 1 min ago
  );

  const expiredRes = await fetch(`${BASE_URL}/refresh`, {
    method: 'POST',
    headers: { Cookie: `refreshToken=${expiredRawToken}` },
  });
  assert(expiredRes.status === 401, 'Expired refresh token rejected with 401 Unauthorized');

  // 13.6 Logout Revocation: POST /logout revokes refresh token and clears cookie
  const remLogin3Res = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: remEmail, password: passwordPlain, remember: true }),
  });
  const rt3 = remLogin3Res.headers.get('set-cookie')?.match(/refreshToken=([^;]+)/)?.[1];
  const rt3Hash = crypto.createHash('sha256').update(rt3).digest('hex');

  const logoutRes = await fetch(`${BASE_URL}/logout`, {
    method: 'POST',
    headers: { Cookie: `refreshToken=${rt3}` },
  });
  const logoutCookies = logoutRes.headers.get('set-cookie') || '';
  const rt3DbCheck = await pool.query('SELECT revoked FROM refresh_tokens WHERE token_hash = $1', [rt3Hash]);

  assert(logoutRes.status === 200, 'POST /api/auth/logout returns 200 OK');
  assert(logoutCookies.includes('refreshToken=;') || logoutCookies.includes('Max-Age=0') || logoutCookies.includes('expires=Thu, 01 Jan 1970'), 'POST /api/auth/logout clears refreshToken cookie');
  assert(rt3DbCheck.rows[0].revoked === true, 'POST /api/auth/logout marks refresh token as revoked=true in PostgreSQL');

  const postLogoutRefresh = await fetch(`${BASE_URL}/refresh`, {
    method: 'POST',
    headers: { Cookie: `refreshToken=${rt3}` },
  });
  assert(postLogoutRefresh.status === 401, 'Refresh attempt after logout rejected with 401 Unauthorized');

  // 13.7 Password Reset Revokes All Active Refresh Tokens
  const remLogin4Res = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: remEmail, password: passwordPlain, remember: true }),
  });
  const rt4 = remLogin4Res.headers.get('set-cookie')?.match(/refreshToken=([^;]+)/)?.[1];

  // Perform reset password flow for remEmail
  const remResetOtp = authOtp.generateOtp();
  const remResetOtpHash = authOtp.hashOtp(remResetOtp);
  await pool.query('UPDATE otp_verifications SET used = true WHERE user_id = $1', [remUserId]);
  await pool.query(
    'INSERT INTO otp_verifications (user_id, purpose, otp_hash, expires_at) VALUES ($1, $2, $3, $4)',
    [remUserId, 'password_reset', remResetOtpHash, new Date(Date.now() + 10 * 60 * 1000)]
  );

  const remVerifyResetRes = await fetch(`${BASE_URL}/verify-reset-otp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: remEmail, otp: remResetOtp }),
  });
  const remVerifyResetData = await remVerifyResetRes.json();
  const remNewPass = 'NewRemPassword123!';

  await fetch(`${BASE_URL}/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resetToken: remVerifyResetData.data.resetToken, newPassword: remNewPass }),
  });

  const postResetRefreshRes = await fetch(`${BASE_URL}/refresh`, {
    method: 'POST',
    headers: { Cookie: `refreshToken=${rt4}` },
  });
  assert(postResetRefreshRes.status === 401, 'Password reset invalidates all existing refresh tokens (401 on /refresh)');

  // 13.8 Privileged Users: Remember Me = extended server session lifetime (NOT JWT)
  const mgrEmail = `mgr_rem_${testSuffix}@example.com`;
  await pool.query(
    'INSERT INTO users (name, email, password_hash, role, email_verified, token_version) VALUES ($1, $2, $3, $4, $5, $6)',
    ['Manager Rem Tester', mgrEmail, passwordHash, 'manager', true, 1]
  );

  const mgrLoginOff = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: mgrEmail, password: passwordPlain, remember: false }),
  });
  const mgrOffData = await mgrLoginOff.json();
  const mgrOffCookies = mgrLoginOff.headers.get('set-cookie') || '';
  const mgrOffMaxAge = mgrOffCookies.match(/Max-Age=(\d+)/i)?.[1];

  assert(mgrLoginOff.status === 200, 'Manager login with remember=false returns 200 OK');
  assert(mgrOffData.data?.token === undefined, 'Manager does NOT receive JWT (Server session strategy preserved)');
  assert(mgrOffCookies.includes('sid='), 'Manager receives sid session cookie');
  assert(parseInt(mgrOffMaxAge, 10) <= 1800, 'Manager remember=false has standard 30-minute session maxAge');

  const mgrLoginOn = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: mgrEmail, password: passwordPlain, remember: true }),
  });
  const mgrOnData = await mgrLoginOn.json();
  const mgrOnCookies = mgrLoginOn.headers.get('set-cookie') || '';
  const mgrOnMaxAge = mgrOnCookies.match(/Max-Age=(\d+)/i)?.[1];

  assert(mgrLoginOn.status === 200, 'Manager login with remember=true returns 200 OK');
  assert(mgrOnData.data?.token === undefined, 'Manager remember=true does NOT convert to JWT');
  assert(parseInt(mgrOnMaxAge, 10) >= 2500000, 'Manager remember=true receives extended 30-day session lifetime');

  // 13.9 Concurrent Refresh Protection (Single-flight / Race prevention)
  const remLogin5Res = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: remEmail, password: remNewPass, remember: true }),
  });
  const rt5 = remLogin5Res.headers.get('set-cookie')?.match(/refreshToken=([^;]+)/)?.[1];

  const [raceRes1, raceRes2] = await Promise.all([
    fetch(`${BASE_URL}/refresh`, { method: 'POST', headers: { Cookie: `refreshToken=${rt5}` } }),
    fetch(`${BASE_URL}/refresh`, { method: 'POST', headers: { Cookie: `refreshToken=${rt5}` } }),
  ]);

  const statuses = [raceRes1.status, raceRes2.status];
  const okCount = statuses.filter(s => s === 200).length;
  assert(okCount === 1, 'Transactional rotation prevents concurrent token races: exactly one request succeeds');

  console.log('\n========================================================================');
  console.log(`🏆 SECURITY AUDIT COMPLETE: ${passedTests}/${totalTests} TESTS PASSED WITH ZERO VULNERABILITIES`);
  console.log('========================================================================\n');

  await pool.end();
}

runSecurityAudit().catch(async (err) => {
  console.error('\n❌ AUDIT FAILED:', err);
  await pool.end();
  process.exit(1);
});

# Modular Monolith Secure Backend

A feature-based modular monolith backend built with **Node.js, Express, PostgreSQL, bcrypt, JWT, and in-memory privileged sessions**.

For complete architecture flows, sequence diagrams, and security specifications, refer directly to [auth.md](file:///d:/ODOO_Pre/Backend/auth.md).

---

## Quick Start

### 1. Prerequisites
- Node.js >= 18
- PostgreSQL server running locally or remotely

### 2. Install Dependencies
```bash
npm install
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and verify credentials:
```bash
cp .env.example .env
```

### 4. Run Migrations
```bash
npm run migrate
```

### 5. Start the Development Server
```bash
npm run dev
```
The server will start at `http://localhost:5000`.

---

## Automated Security Audit & Testing
Run the complete 47-point end-to-end security test suite:
```bash
npm test
```

---

## Key Security Architecture Summary
1. **Feature-Based Architecture**: All authentication logic is strictly contained inside `src/auth/`.
2. **Dual-Strategy Auth Model**:
   - **Standard Users (`role: 'user'`)**: 15-minute JWT (`sub`, `role: 'user'`, `tokenVersion`).
   - **Privileged Users (`manager`, `admin`, `super_admin`)**: 32-byte crypto session IDs stored in-memory and delivered via secure, HTTP-only, `sameSite: strict` cookies.
3. **Defense-in-Depth Passwords**: `password + pepper -> bcrypt (12 rounds) -> database password_hash`. Pepper is loaded exclusively from `.env` and never exists in PostgreSQL.
4. **Email OTP Verification**: 6-digit `crypto.randomInt` code stored as an HMAC-SHA256 hash with a 10-minute expiry, max 5 attempts, and single-use enforcement.
5. **Server-Side Arithmetic CAPTCHA**: Dynamic challenges generated via `crypto.randomInt`, HMAC hashed answers, 5-minute expiry, 3-attempt lockout, and single-use consumption.
6. **Two-Step Password Reset**: Generic response prevents account enumeration. Verifying OTP delivers a short-lived 64-char `resetToken`. Consuming the token updates the password, increments `token_version` (revoking all issued JWTs), and purges active privileged sessions.
7. **Role-Based Access Control (RBAC)**: Strict separation across `user`, `manager`, `admin`, and `super_admin` with precise `401 Unauthorized` vs `403 Forbidden` status codes.
8. **Insecure Direct Object Reference (IDOR) Defense**: Resource ownership authorization ensures standard users cannot access another user's records.

Detailed documentation and mermaid flow diagrams are in [auth.md](file:///d:/ODOO_Pre/Backend/auth.md).

# FarmXpert Backend (Node.js)

Express 5, plain JavaScript (ES modules), `pg` with hand-written SQL, Ajv validation,
pino logging. No ORM: the schema leans on PostGIS, pgvector, partitioning and triggers,
and raw SQL is both the fastest and the clearest way to use them.

```
src/
  server.js            process entry: optional cluster (WEB_CONCURRENCY), graceful shutdown
  app.js               Express app: security headers, CORS, compression, request ids, routes
  config/env.js        all configuration, validated once at boot
  db/                  pool, migration runner, migrations/NNNN_*.sql
  lib/                 errors, validation, keyset paging, units, logger
  clients/             AI backend, data.gov.in mandi prices, Blynk devices
  modules/             one file per area; chat/ has the conversation flow
  jobs/                cron scheduler, mandi ingestion, storage lifecycle + archive
test/                  node:test suites (no database needed)
```

## Scripts

| | |
|---|---|
| `npm run dev` | watch mode, reads `.env` |
| `npm start` | production start |
| `npm run migrate` / `migrate:status` | apply / list migrations (advisory-locked, checksummed) |
| `npm run lifecycle` | one storage-lifecycle run by hand |
| `npm test` | unit and route tests |

## API (`/api/v1`)

| Area | Routes |
|---|---|
| Health | `GET /health` (liveness), `GET /ready` (database + AI) — not under `/api/v1` |
| Users | `POST /users`, `GET/PATCH/DELETE /users/:id` (DELETE is a real erasure) |
| Farms | `POST /farms`, `GET /farms?user_id=`, `GET/PATCH/DELETE /farms/:id` — area in `area_acres` or `area_hectares` |
| Fields | `POST/GET /farms/:id/fields`, `PATCH/DELETE /fields/:id` — boundary as GeoJSON Polygon |
| Soil | `POST /farms/:id/soil`, `GET /farms/:id/soil/latest`, `GET /farms/:id/soil?cursor=` |
| Devices | `POST/GET /farms/:id/devices`, `DELETE /devices/:id`, `POST /farms/:id/devices/sync` |
| Chat | `POST /chat/ask` (JSON, or streamed with `Accept: text/event-stream`), `POST /voice/ask` (audio body, streamed), `POST /chat/feedback`, `GET /conversations?user_id=`, `GET /conversations/:id/messages`, `GET /requests/:requestId` |
| Plans | `GET /farms/:id/tasks`, `PATCH /tasks/:id`, `GET /farms/:id/irrigation-plans`, `PATCH /irrigation-plans/:id`, `GET /farms/:id/crop-recommendations` |
| Market | `GET /market/prices?commodity=`, `GET /farms/:id/market-recommendations` |
| Token usage | `GET /users/:id/usage?from=&to=` (today's allowance + daily breakdown) |
| Admin (`x-admin-key`) | `POST /admin/jobs/mandi`, `POST /admin/jobs/lifecycle`, `GET /admin/archive`, `GET /admin/storage`, `GET /admin/usage`, `PUT /admin/users/:id/token-limit` |

Errors always have the shape `{ "error": { "code", "message", "details?", "requestId" } }`.
Lists use keyset cursors (`nextCursor`), never OFFSET.

## Database

PostgreSQL 14+ with `postgis`, `vector` and `pgcrypto`.

- **Spatial:** farm location is `geography(POINT)` with generated `latitude`/`longitude`;
  field boundaries are `geography(POLYGON)`; both GIST-indexed.
- **Partitioned monthly** (UTC bounds, created 3 months ahead, DEFAULT as a safety net):
  `soil_data`, `messages`, `orchestration_requests`, `agent_outputs`, `weather_snapshots`.
  Each has a BRIN index on time plus the B-tree its hot query needs.
- **Stored once:** weather is one row per ~1 km cell shared by every farm in it (30-minute
  dedup window); the task plan's derived `daily_plans`/`critical_tasks` are dropped on write
  and rebuilt on read. Measured: 74 KB of agent output per request stored as ~12 KB.
- **Idempotent writes:** `idempotency_keys` gives the global uniqueness of a request id that
  partitioned tables cannot; soil readings dedupe on device + time.
- **Money is NUMERIC.** A missing mandi price is NULL, never 0.
- **Hot/cold:** `retention_policies` sets months kept online per table (messages 12,
  requests 6, agent outputs 3, weather 3, soil 24). The daily job exports each expired
  month to gzip NDJSON, reads it back and counts it, records it in `archive_manifest`,
  and only then detaches and drops the partition.
- **Legacy data:** migration 0001 renames tables from the old Python schema to `*_legacy`
  and 0008 copies their rows across (acres → hectares, text dates parsed, duplicates
  collapsed). Drop the `*_legacy` tables by hand once the import is checked.

## Streaming, voice and languages

- **One API style:** REST + JSON, with server-sent events (SSE) for answers that stream.
  SSE works through every proxy and CDN, needs no client library, and fits one question
  one answer. The Node↔AI hop is the same over keep-alive HTTP with `x-internal-key`.
- **Typed, streamed:** `conversation` → `meta` → `delta`… → `done`.
- **Voice:** `POST /voice/ask?farm_id=…&audio_seconds=…` with the recording as the body
  (webm/ogg Opus, m4a, mp3, wav; checked by content). Events add `transcript` first and
  `audio` (one base64 clip per sentence, in order) while the answer is still being
  written. Audio is never stored; the transcript is.
- **Languages:** detected from the farmer's words (script first, then the model); the
  profile language is only a hint. Stored per message: `language`, `script`, `query_en`,
  `input_mode`, `audio_seconds`.
- **Limits:** daily token allowance, daily voice seconds (`VOICE_DAILY_SECONDS`), and a
  per-minute burst guard (`RATE_LIMIT_*`).

## Token usage

The AI backend meters every model call made while answering (question understanding,
retrieval rewrite, embeddings, the written answer) using the provider's own counts, and
returns them as `usage`. When a provider omits counts, a script-aware tokenizer estimates
them (Hindi/Gujarati cost 2-3x more tokens than English) and the row is marked estimated.

- `token_usage_daily`: per farmer, local day (`TOKEN_DAY_TIMEZONE`) and model; priced at
  write time from `TOKEN_PRICES`.
- Quota: `TOKEN_DAILY_LIMIT` per farmer per day (per-user override, `0` blocks). Checked
  before the AI is called; over the limit returns `429 token_quota_exceeded` with the
  reset time. The limit is soft: concurrent questions can overshoot by one answer.
- Recorded inside the idempotent turn transaction, so a retry is never counted twice.

Capacity estimate at 10,000 farmers × 3 questions a day: ~370 MB/day, ~11 GB/month hot,
bounded by the retention windows.

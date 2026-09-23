-- 0009 Token usage: per-request detail, per-user daily totals, quotas.
--
-- The AI backend reports the provider's own token counts for every model call
-- made while answering (understanding, retrieval, embeddings, the answer).
-- Node stores them three ways, each for one question:
--   messages.prompt/completion_tokens  "what did this answer cost"
--   orchestration_requests.usage       the per-model breakdown of one run
--   token_usage_daily                  "how much has this farmer used today",
--                                      read on every question to enforce the
--                                      quota, so it is one PK lookup, not a
--                                      scan of partitioned history.

ALTER TABLE orchestration_requests
    ADD COLUMN usage jsonb,
    ADD COLUMN total_tokens integer;

-- NULL means the deployment default (TOKEN_DAILY_LIMIT); 0 means blocked.
ALTER TABLE users
    ADD COLUMN token_daily_limit integer,
    ADD CONSTRAINT ck_users_token_daily_limit_positive CHECK (token_daily_limit IS NULL OR token_daily_limit >= 0);

CREATE TABLE token_usage_daily (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- The farmer's local day (TOKEN_DAY_TIMEZONE, India by default), so a
    -- quota resets at midnight where the farmer is, not at 05:30 IST.
    usage_date        date        NOT NULL,
    -- NULL: turns asked without an account, kept so totals are complete.
    user_id           uuid        REFERENCES users (id) ON DELETE CASCADE,
    model             varchar(120) NOT NULL,
    purpose           varchar(12) NOT NULL,
    prompt_tokens     bigint      NOT NULL DEFAULT 0,
    completion_tokens bigint      NOT NULL DEFAULT 0,
    total_tokens      bigint      GENERATED ALWAYS AS (prompt_tokens + completion_tokens) STORED,
    calls             integer     NOT NULL DEFAULT 0,
    estimated_calls   integer     NOT NULL DEFAULT 0,
    -- Priced when written, at the price in force then: a later price change
    -- must not rewrite what past usage cost.
    cost              numeric(14, 6) NOT NULL DEFAULT 0,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_token_usage_daily_purpose_known CHECK (purpose IN ('chat', 'embedding')),
    CONSTRAINT ck_token_usage_daily_counts_positive CHECK (
        prompt_tokens >= 0 AND completion_tokens >= 0 AND calls >= 0 AND estimated_calls >= 0 AND cost >= 0)
);
-- One row per farmer, day and model. COALESCE folds anonymous usage into a
-- single row per day (a plain unique key treats every NULL as distinct).
CREATE UNIQUE INDEX uq_token_usage_daily_key ON token_usage_daily
    (usage_date, COALESCE(user_id, '00000000-0000-0000-0000-000000000000'::uuid), model);
-- The quota check and the farmer's usage screen.
CREATE INDEX ix_token_usage_daily_user_date ON token_usage_daily (user_id, usage_date DESC)
    WHERE user_id IS NOT NULL;
CREATE INDEX ix_token_usage_daily_date ON token_usage_daily (usage_date DESC);
ALTER TABLE token_usage_daily SET (fillfactor = 80);   -- updated on every question

CREATE TRIGGER trg_token_usage_daily_set_updated_at BEFORE UPDATE ON token_usage_daily
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

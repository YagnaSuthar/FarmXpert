-- 0006 Mandi prices, device credentials, and the knowledge index.

-- Prices are NUMERIC: float cannot hold 2310.10 exactly, and a farmer's price
-- is not a number to be approximately right about. The natural key makes
-- ingestion idempotent - a re-fetch corrects a price instead of duplicating
-- it, which would also silently weight the average the forecast is built on.
CREATE TABLE mandi_price_data (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    farm_id      uuid        REFERENCES farms (id) ON DELETE SET NULL,
    commodity    varchar(100) NOT NULL,
    market       varchar(100) NOT NULL,
    state        varchar(80),
    district     varchar(80),
    arrival_date date        NOT NULL,
    min_price    numeric(12, 2),
    max_price    numeric(12, 2),
    modal_price  numeric(12, 2),
    -- '' rather than NULL: NULL is never equal to NULL, so a NULL variety
    -- would slip past the unique key.
    variety      varchar(100) NOT NULL DEFAULT '',
    grade        varchar(50)  NOT NULL DEFAULT '',
    source       varchar(50)  NOT NULL DEFAULT 'AGMARKNET',
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_mandi_price_data_observation UNIQUE (commodity, market, arrival_date, variety, grade),
    CONSTRAINT ck_mandi_price_data_min_price_positive CHECK (min_price IS NULL OR min_price >= 0),
    CONSTRAINT ck_mandi_price_data_modal_price_positive CHECK (modal_price IS NULL OR modal_price >= 0),
    CONSTRAINT ck_mandi_price_data_max_price_above_min CHECK (
        min_price IS NULL OR max_price IS NULL OR max_price >= min_price),
    CONSTRAINT ck_mandi_price_data_modal_price_between CHECK (
        modal_price IS NULL OR min_price IS NULL OR max_price IS NULL
        OR modal_price BETWEEN min_price AND max_price)
);
-- The question the market screen asks: this commodity, most recent first.
-- lower(): the API matches commodity names case-insensitively, through this index.
CREATE INDEX ix_mandi_price_data_commodity_arrival_date ON mandi_price_data (lower(commodity), arrival_date DESC);
CREATE INDEX ix_mandi_price_data_state_district ON mandi_price_data (state, district, arrival_date DESC);
CREATE INDEX ix_mandi_price_data_arrival_date_brin ON mandi_price_data USING brin (arrival_date);

CREATE TABLE market_recommendations (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    farm_id         uuid        REFERENCES farms (id) ON DELETE CASCADE,
    commodity       varchar(100) NOT NULL,
    location        varchar(120),
    best_market     varchar(100),
    best_price      numeric(12, 2),
    forecast_trend  varchar(20),
    predicted_price numeric(12, 2),
    recommendation  varchar(24) NOT NULL,
    confidence      double precision,
    reasoning       jsonb,
    agent_version   varchar(20),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_market_recommendations_confidence_in_range CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    CONSTRAINT ck_market_recommendations_recommendation_known CHECK (
        recommendation IN ('SELL_NOW', 'SELL_IN_OTHER_MANDI', 'HOLD')),
    CONSTRAINT ck_market_recommendations_best_price_positive CHECK (best_price IS NULL OR best_price >= 0)
);
CREATE INDEX ix_market_recommendations_farm_id_created_at ON market_recommendations (farm_id, created_at DESC);

-- A token is a credential: never logged, never returned by the API.
CREATE TABLE blynk_tokens (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    farm_id      uuid        NOT NULL REFERENCES farms (id) ON DELETE CASCADE,
    token        varchar(100) NOT NULL UNIQUE,
    label        varchar(80),
    is_active    boolean     NOT NULL DEFAULT true,
    revoked_at   timestamptz,
    -- A device that has gone silent is a farm with no data; this shows it.
    last_seen_at timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_blynk_tokens_token_long_enough CHECK (char_length(token) >= 8)
);
COMMENT ON COLUMN blynk_tokens.token IS 'SECRET. Never log this and never return it from an API.';
-- One ACTIVE token per farm; revoked ones stay for the audit trail. A plain
-- unique constraint would forbid ever rotating a token.
CREATE UNIQUE INDEX uq_blynk_tokens_farm_active ON blynk_tokens (farm_id) WHERE is_active;

-- The retrieval agent's discovery index. Written by the AI backend's reindex,
-- read on every knowledge question. HNSW rather than IVFFlat: IVFFlat must be
-- built after data exists and is poor on an empty table, which is exactly how
-- every fresh deployment starts. Dimension matches nvidia/nv-embedqa-e5-v5.
CREATE TABLE knowledge_chunks (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id    varchar(128) NOT NULL UNIQUE,
    doc_id      varchar(128) NOT NULL,
    title       varchar(300) NOT NULL,
    text        text        NOT NULL,
    source      varchar(16) NOT NULL DEFAULT 'okf',
    crops       jsonb       NOT NULL DEFAULT '[]'::jsonb,
    embedding   vector(1024) NOT NULL,
    token_count integer,
    indexed_at  timestamptz NOT NULL DEFAULT now(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_knowledge_chunks_text_not_blank CHECK (char_length(btrim(text)) > 0),
    CONSTRAINT ck_knowledge_chunks_source_known CHECK (source IN ('okf', 'index', 'external'))
);
CREATE INDEX ix_knowledge_chunks_embedding ON knowledge_chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX ix_knowledge_chunks_doc_id ON knowledge_chunks (doc_id);
CREATE INDEX ix_knowledge_chunks_crops ON knowledge_chunks USING gin (crops);

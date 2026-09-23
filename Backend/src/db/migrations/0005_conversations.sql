-- 0005 Conversations, orchestration runs, agent outputs, weather snapshots.
--
-- Sized from a measured number: 74 KB of agent output per request, 12 KB
-- stored after canonical form, shared weather and lz4 (~370 MB/day at 10,000
-- farmers). Monthly partitions on everything high-volume; `conversations` is a
-- small, often-updated table and stays plain.

CREATE TABLE conversations (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid        REFERENCES users (id) ON DELETE CASCADE,
    farm_id         uuid        REFERENCES farms (id) ON DELETE SET NULL,
    field_id        uuid        REFERENCES fields (id) ON DELETE SET NULL,
    channel         varchar(16) NOT NULL DEFAULT 'app',
    language        varchar(12) NOT NULL DEFAULT 'en',
    title           varchar(160),
    status          varchar(12) NOT NULL DEFAULT 'open',
    message_count   integer     NOT NULL DEFAULT 0,
    -- Messages cannot predate their thread: history queries bound by this
    -- skip every monthly partition older than the conversation.
    started_at      timestamptz NOT NULL DEFAULT now(),
    last_message_at timestamptz NOT NULL DEFAULT now(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_conversations_channel_known CHECK (channel IN ('app', 'whatsapp', 'voice', 'sms', 'web', 'mcp', 'api')),
    CONSTRAINT ck_conversations_status_known CHECK (status IN ('open', 'closed', 'archived')),
    CONSTRAINT ck_conversations_message_count_positive CHECK (message_count >= 0)
);
CREATE INDEX ix_conversations_user_id_last_message_at ON conversations (user_id, last_message_at DESC, id DESC);
CREATE INDEX ix_conversations_farm_id_last_message_at ON conversations (farm_id, last_message_at DESC, id DESC);
-- Updated on every message: room on each page for in-place (HOT) updates, so
-- the counter does not rewrite index entries every time.
ALTER TABLE conversations SET (fillfactor = 80);

-- The farmer's words and FarmXpert's answers. Farmer text is personal data
-- (DPDP Act): it lives here and nowhere else.
CREATE TABLE messages (
    id                uuid        NOT NULL DEFAULT gen_random_uuid(),
    created_at        timestamptz NOT NULL DEFAULT now(),
    conversation_id   uuid        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    role              varchar(12) NOT NULL,
    content           text        NOT NULL,
    language          varchar(12),
    request_id        varchar(64),
    intent            varchar(24),
    model             varchar(80),
    prompt_tokens     integer,
    completion_tokens integer,
    latency_ms        numeric(10, 2),
    feedback          smallint,
    CONSTRAINT pk_messages PRIMARY KEY (id, created_at),
    CONSTRAINT ck_messages_role_known CHECK (role IN ('farmer', 'assistant', 'system', 'tool')),
    CONSTRAINT ck_messages_content_bounded CHECK (char_length(content) <= 20000),
    CONSTRAINT ck_messages_latency_positive CHECK (latency_ms IS NULL OR latency_ms >= 0),
    CONSTRAINT ck_messages_feedback_known CHECK (feedback IS NULL OR feedback BETWEEN -1 AND 1)
) PARTITION BY RANGE (created_at);
SELECT farmxpert_rolling_partitions('messages');
-- History, newest first, resumable by a (created_at, id) keyset cursor.
CREATE INDEX ix_messages_conversation_id_created_at ON messages (conversation_id, created_at DESC, id DESC);
CREATE INDEX ix_messages_request_id ON messages (request_id) WHERE request_id IS NOT NULL;
CREATE INDEX ix_messages_created_at_brin ON messages USING brin (created_at);

-- Keep message_count and last_message_at exact for every writer.
CREATE OR REPLACE FUNCTION bump_conversation() RETURNS trigger AS $$
BEGIN
    UPDATE conversations
       SET message_count   = message_count + 1,
           last_message_at = GREATEST(last_message_at, NEW.created_at)
     WHERE id = NEW.conversation_id;
    RETURN NULL;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_messages_bump_conversation
    AFTER INSERT ON messages FOR EACH ROW EXECUTE FUNCTION bump_conversation();

CREATE TABLE orchestration_requests (
    id               uuid        NOT NULL DEFAULT gen_random_uuid(),
    created_at       timestamptz NOT NULL DEFAULT now(),
    request_id       varchar(64) NOT NULL,
    conversation_id  uuid        REFERENCES conversations (id) ON DELETE SET NULL,
    farm_id          uuid        REFERENCES farms (id) ON DELETE SET NULL,
    field_id         uuid        REFERENCES fields (id) ON DELETE SET NULL,
    intents          jsonb,
    status           varchar(20) NOT NULL,
    summary          text,
    confidence       double precision,
    duration_ms      numeric(10, 2) NOT NULL,
    agents_succeeded smallint    NOT NULL DEFAULT 0,
    agents_failed    smallint    NOT NULL DEFAULT 0,
    agents_skipped   smallint    NOT NULL DEFAULT 0,
    conflicts        jsonb,
    execution        jsonb,
    CONSTRAINT pk_orchestration_requests PRIMARY KEY (id, created_at),
    CONSTRAINT ck_orchestration_requests_status_known CHECK (
        status IN ('success', 'partial_success', 'failed', 'validation_error')),
    CONSTRAINT ck_orchestration_requests_confidence_in_range CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    CONSTRAINT ck_orchestration_requests_duration_positive CHECK (duration_ms >= 0)
) PARTITION BY RANGE (created_at);
SELECT farmxpert_rolling_partitions('orchestration_requests');
CREATE INDEX ix_orchestration_requests_request_id ON orchestration_requests (request_id);
CREATE INDEX ix_orchestration_requests_farm_id_created_at ON orchestration_requests (farm_id, created_at DESC)
    WHERE farm_id IS NOT NULL;
CREATE INDEX ix_orchestration_requests_conversation_id ON orchestration_requests (conversation_id)
    WHERE conversation_id IS NOT NULL;
-- "What failed in the last hour" must not scan the successes.
CREATE INDEX ix_orchestration_requests_failures ON orchestration_requests (created_at DESC)
    WHERE status <> 'success';
CREATE INDEX ix_orchestration_requests_created_at_brin ON orchestration_requests USING brin (created_at);

-- One row per agent per request: the payload that explains the advice.
CREATE TABLE agent_outputs (
    id                  uuid        NOT NULL DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    request_id          varchar(64) NOT NULL,
    farm_id             uuid        REFERENCES farms (id) ON DELETE SET NULL,
    agent               varchar(60) NOT NULL,
    agent_version       varchar(20),
    status              varchar(32) NOT NULL,
    error_code          varchar(40),
    attempts            smallint    NOT NULL DEFAULT 1,
    duration_ms         numeric(10, 2) NOT NULL,
    confidence          double precision,
    data_age_s          double precision,
    payload             jsonb,
    payload_bytes       integer,
    -- Weather is referenced, not copied: stored once per cell below.
    weather_snapshot_id uuid,
    weather_snapshot_at timestamptz,
    CONSTRAINT pk_agent_outputs PRIMARY KEY (id, created_at),
    CONSTRAINT ck_agent_outputs_duration_positive CHECK (duration_ms >= 0),
    CONSTRAINT ck_agent_outputs_confidence_in_range CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    CONSTRAINT ck_agent_outputs_attempts_plausible CHECK (attempts BETWEEN 1 AND 20)
) PARTITION BY RANGE (created_at);
SELECT farmxpert_rolling_partitions('agent_outputs');
CREATE INDEX ix_agent_outputs_request_id ON agent_outputs (request_id);
CREATE INDEX ix_agent_outputs_agent_created_at ON agent_outputs (agent, created_at DESC);
CREATE INDEX ix_agent_outputs_farm_id_agent_created_at ON agent_outputs (farm_id, agent, created_at DESC)
    WHERE farm_id IS NOT NULL;
CREATE INDEX ix_agent_outputs_failures ON agent_outputs (agent, created_at DESC) WHERE status <> 'success';
CREATE INDEX ix_agent_outputs_created_at_brin ON agent_outputs USING brin (created_at);

-- One forecast per ~1 km cell, shared by every farm inside it. Dedup is a
-- lookup on (cell_key, content_hash) within the cache window, not a unique
-- constraint: on a partitioned table a unique index must include created_at,
-- which would make every row unique and forbid nothing.
CREATE TABLE weather_snapshots (
    id           uuid        NOT NULL DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    cell_key     varchar(24) NOT NULL,
    cell         geography(POINT, 4326),
    content_hash varchar(64) NOT NULL,
    provider     varchar(40),
    status       varchar(16),
    forecast     jsonb       NOT NULL,
    reuse_count  integer     NOT NULL DEFAULT 1,
    CONSTRAINT pk_weather_snapshots PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);
SELECT farmxpert_rolling_partitions('weather_snapshots');
CREATE INDEX ix_weather_snapshots_cell_key_content_hash ON weather_snapshots (cell_key, content_hash, created_at DESC);
CREATE INDEX ix_weather_snapshots_cell ON weather_snapshots USING gist (cell);
CREATE INDEX ix_weather_snapshots_created_at_brin ON weather_snapshots USING brin (created_at);

-- Global uniqueness of request_id, which a partitioned table cannot enforce.
-- A client retry is recognised here and stored once. Purged after 48 hours.
CREATE TABLE idempotency_keys (
    request_id  varchar(64) PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    recorded_at timestamptz NOT NULL
);
CREATE INDEX ix_idempotency_keys_created_at ON idempotency_keys (created_at);

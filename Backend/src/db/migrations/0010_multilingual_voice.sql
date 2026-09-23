-- 0010 Multilingual knowledge search, how each question was read, and voice.

-- Which model produced each vector. Vectors from two models live in different
-- spaces: comparing them gives confident nonsense. Search reads only rows of
-- the configured model, so switching models (NVIDIA -> OpenAI) is safe even
-- while the reindex is still running - un-migrated rows are simply not found.
ALTER TABLE knowledge_chunks
    ADD COLUMN embed_model varchar(120) NOT NULL DEFAULT 'nvidia/nv-embedqa-e5-v5';
ALTER TABLE knowledge_chunks ALTER COLUMN embed_model DROP DEFAULT;
CREATE INDEX ix_knowledge_chunks_embed_model ON knowledge_chunks (embed_model);

-- How the farmer's question was read: needed to answer "which languages fail",
-- and to show support staff what the model understood.
ALTER TABLE messages
    ADD COLUMN script varchar(8),
    ADD COLUMN query_en text,
    ADD COLUMN input_mode varchar(8) NOT NULL DEFAULT 'text',
    ADD COLUMN audio_seconds numeric(8, 2),
    ADD CONSTRAINT ck_messages_input_mode_known CHECK (input_mode IN ('text', 'voice')),
    ADD CONSTRAINT ck_messages_audio_seconds_positive CHECK (audio_seconds IS NULL OR audio_seconds >= 0),
    ADD CONSTRAINT ck_messages_query_en_bounded CHECK (query_en IS NULL OR char_length(query_en) <= 4000);

-- Usage is no longer only tokens: speech-to-text bills by audio seconds and
-- text-to-speech by characters. One table, one quota, one report.
ALTER TABLE token_usage_daily
    DROP CONSTRAINT ck_token_usage_daily_purpose_known,
    ADD CONSTRAINT ck_token_usage_daily_purpose_known
        CHECK (purpose IN ('chat', 'embedding', 'transcription', 'speech')),
    ADD COLUMN audio_seconds numeric(12, 2) NOT NULL DEFAULT 0,
    ADD COLUMN characters bigint NOT NULL DEFAULT 0,
    ADD CONSTRAINT ck_token_usage_daily_media_positive CHECK (audio_seconds >= 0 AND characters >= 0);

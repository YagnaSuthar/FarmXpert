-- 0001 Foundation: extensions, shared functions, and moving old tables aside.
--
-- pgcrypto  gen_random_uuid() for server-side primary keys
-- postgis   geography, spatial indexes
-- vector    embeddings and HNSW for the knowledge index
--
-- A managed provider may need these enabled by an administrator; if so this
-- fails here, loudly, instead of half-creating a schema.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

-- Keeps updated_at true for every writer: the API, a bulk UPDATE, a fix in
-- psql. An application-side "onupdate" misses all but the first.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END $$ LANGUAGE plpgsql;

-- Monthly partitions for [from_month, to_month], plus a DEFAULT safety net.
--
-- Bounds are written with an explicit +00 offset. A bare date literal is read
-- in the session's timezone; this system runs both IST and UTC sessions, and
-- partitions created from both would overlap by five and a half hours.
CREATE OR REPLACE FUNCTION farmxpert_create_monthly_partitions(
    parent text, from_month date, to_month date)
RETURNS integer AS $$
DECLARE
    m       date := date_trunc('month', from_month)::date;
    last    date := date_trunc('month', to_month)::date;
    part    text;
    created integer := 0;
BEGIN
    WHILE m <= last LOOP
        part := format('%s_%s', parent, to_char(m, 'YYYY_MM'));
        IF to_regclass(part) IS NULL THEN
            EXECUTE format(
                'CREATE TABLE %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                part, parent,
                m::text || ' 00:00:00+00',
                (m + interval '1 month')::date::text || ' 00:00:00+00');
            -- Append-mostly: vacuum and analyse sooner than the global default,
            -- so the newest (busiest) month never plans from stale statistics.
            EXECUTE format(
                'ALTER TABLE %I SET (autovacuum_vacuum_scale_factor = 0.05, '
                'autovacuum_analyze_scale_factor = 0.02)', part);
            created := created + 1;
        END IF;
        m := (m + interval '1 month')::date;
    END LOOP;

    part := parent || '_default';
    IF to_regclass(part) IS NULL THEN
        EXECUTE format('CREATE TABLE %I PARTITION OF %I DEFAULT', part, parent);
    END IF;
    RETURN created;
END $$ LANGUAGE plpgsql;

-- The rolling window used by migrations and by the daily lifecycle job.
CREATE OR REPLACE FUNCTION farmxpert_rolling_partitions(parent text)
RETURNS integer AS $$
    SELECT farmxpert_create_monthly_partitions(
        parent,
        (date_trunc('month', now() AT TIME ZONE 'UTC') - interval '1 month')::date,
        (date_trunc('month', now() AT TIME ZONE 'UTC') + interval '3 months')::date);
$$ LANGUAGE sql;

-- ── Move tables from the old Python schema aside ───────────────────────────
-- Each is recognised by a column only the old shape had. Renamed, never
-- dropped: 0008 copies their rows into the new tables. A fresh database has
-- none of these and this block does nothing.
DO $$
DECLARE
    legacy record;
BEGIN
    FOR legacy IN
        SELECT * FROM (VALUES
            ('users',                  'created_at',        false),
            ('farms',                  'farm_size_acres',   true),
            ('soil_data',              'soil_health_score', true),
            ('crops',                  'slug',              false),
            ('crop_history',           'yield_per_acre',    true),
            ('crop_recommendations',   'top_crop',          false),
            ('market_recommendations', 'agent_version',     false),
            ('mandi_price_data',       'updated_at',        false),
            ('blynk_tokens',           'revoked_at',        false)
        ) AS t(tbl, marker, marker_means_legacy)
    LOOP
        IF to_regclass('public.' || legacy.tbl) IS NULL THEN
            CONTINUE;
        END IF;
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = legacy.tbl
                     AND column_name = legacy.marker) = legacy.marker_means_legacy THEN
            EXECUTE format('ALTER TABLE %I RENAME TO %I', legacy.tbl, legacy.tbl || '_legacy');
            RAISE NOTICE 'Moved old table % aside as %_legacy', legacy.tbl, legacy.tbl;
        END IF;
    END LOOP;
END $$;

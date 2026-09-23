-- 0007 Hot/cold lifecycle, compression and updated_at triggers.
--
-- A monthly partition older than its table's hot window is exported to the
-- archive (gzip NDJSON), read back and row-counted, recorded in
-- archive_manifest, and only then dropped. Nothing is dropped unverified.

CREATE TABLE retention_policies (
    table_name   varchar(63) PRIMARY KEY,
    hot_months   integer     NOT NULL,
    -- 'archive' exports then drops; 'drop' discards (derived, rebuildable data).
    cold_action  varchar(12) NOT NULL DEFAULT 'archive',
    enabled      boolean     NOT NULL DEFAULT true,
    notes        text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_retention_policies_hot_months_positive CHECK (hot_months >= 1),
    CONSTRAINT ck_retention_policies_cold_action_known CHECK (cold_action IN ('archive', 'drop'))
);

INSERT INTO retention_policies (table_name, hot_months, cold_action, notes) VALUES
    ('messages',               12, 'archive', 'Farmer history: a year online, then cold.'),
    ('orchestration_requests',  6, 'archive', 'Run metadata; failures are what is queried.'),
    ('agent_outputs',           3, 'archive', 'Largest by bytes; explains past advice.'),
    ('weather_snapshots',       3, 'archive', 'Forecasts as they were given.'),
    ('soil_data',              24, 'archive', 'Two seasons of readings stay queryable.')
ON CONFLICT (table_name) DO NOTHING;

CREATE TABLE archive_manifest (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name     varchar(63) NOT NULL,
    partition_name varchar(63) NOT NULL,
    range_start    timestamptz NOT NULL,
    range_end      timestamptz NOT NULL,
    uri            text,
    row_count      bigint,
    bytes          bigint,
    sha256         varchar(64),
    status         varchar(12) NOT NULL DEFAULT 'exporting',
    error          text,
    started_at     timestamptz NOT NULL DEFAULT now(),
    finished_at    timestamptz,
    CONSTRAINT uq_archive_manifest_partition UNIQUE (partition_name),
    CONSTRAINT ck_archive_manifest_status_known CHECK (
        status IN ('exporting', 'verified', 'dropped', 'failed')),
    CONSTRAINT ck_archive_manifest_range_ordered CHECK (range_end > range_start)
);
CREATE INDEX ix_archive_manifest_table_range ON archive_manifest (table_name, range_start);

-- lz4 decompresses several times faster than the default pglz on the large
-- JSON payloads. Older servers or builds without lz4 keep pglz.
DO $$
DECLARE
    target record;
BEGIN
    IF current_setting('server_version_num')::int < 140000 THEN
        RETURN;
    END IF;
    FOR target IN SELECT * FROM (VALUES
        ('agent_outputs', 'payload'), ('weather_snapshots', 'forecast'),
        ('orchestration_requests', 'execution'), ('messages', 'content'),
        ('task_plans', 'plan'), ('irrigation_plans', 'plan'))
        AS t(tbl, col)
    LOOP
        BEGIN
            EXECUTE format('ALTER TABLE %I ALTER COLUMN %I SET COMPRESSION lz4', target.tbl, target.col);
        EXCEPTION WHEN feature_not_supported OR invalid_parameter_value THEN
            RAISE NOTICE 'lz4 unavailable; % keeps pglz', target.tbl;
        END;
    END LOOP;
END $$;

-- updated_at maintained by the database, so no writer can forget it.
DO $$
DECLARE
    tbl text;
BEGIN
    FOR tbl IN
        SELECT c.table_name FROM information_schema.columns c
          JOIN information_schema.tables t
            ON t.table_schema = c.table_schema AND t.table_name = c.table_name
         WHERE c.table_schema = current_schema()
           AND c.column_name = 'updated_at'
           AND t.table_type = 'BASE TABLE'
           AND c.table_name NOT LIKE '%\_legacy' ESCAPE '\'
           AND NOT EXISTS (SELECT 1 FROM pg_inherits i
                             JOIN pg_class child ON child.oid = i.inhrelid
                            WHERE child.relname = c.table_name)
    LOOP
        EXECUTE format('CREATE TRIGGER trg_%s_set_updated_at BEFORE UPDATE ON %I
                        FOR EACH ROW EXECUTE FUNCTION set_updated_at()', tbl, tbl);
    END LOOP;
END $$;
-- The loop covers partitioned parents (soil_data) too: information_schema lists
-- them as BASE TABLE, and a trigger on the parent applies to every partition.

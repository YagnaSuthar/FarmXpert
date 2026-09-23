-- 0003 Soil readings (partitioned) and their analyses.
--
-- One probe every 15 minutes is ~96 rows a day per farm: at 10,000 farms,
-- a million rows a day - the largest table by row count. Monthly partitions
-- by the MEASUREMENT time keep each month's indexes small and let old seasons
-- move to cold storage. PostgreSQL requires the partition key in the primary
-- key, hence (id, recorded_at).
--
-- Measurements are facts and never change. The agent's opinion of them lives
-- in soil_analyses, so the agent can be improved and re-run over history
-- without rewriting what the sensor actually said.

CREATE TABLE soil_data (
    id                      uuid        NOT NULL DEFAULT gen_random_uuid(),
    farm_id                 uuid        NOT NULL REFERENCES farms (id) ON DELETE CASCADE,
    field_id                uuid        REFERENCES fields (id) ON DELETE SET NULL,
    recorded_at             timestamptz NOT NULL DEFAULT now(),
    source                  varchar(16) NOT NULL DEFAULT 'sensor',
    device_id               varchar(64),
    soil_moisture           double precision,
    soil_temperature        double precision,
    soil_ph                 double precision,
    electrical_conductivity double precision,
    nitrogen                double precision,
    phosphorus              double precision,
    potassium               double precision,
    air_temperature         double precision,
    air_humidity            double precision,
    soil_type               varchar(50),
    crop_type               varchar(50),
    rainfall                double precision,
    irrigation_type         varchar(50),
    irrigation_amount       double precision,
    fertilizer_type         varchar(100),
    fertilizer_amount       numeric(10, 2),
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_soil_data PRIMARY KEY (id, recorded_at),
    CONSTRAINT ck_soil_data_source_known CHECK (source IN ('sensor', 'lab', 'manual', 'estimated')),
    -- A reading outside these is instrument error, not an unusual field.
    CONSTRAINT ck_soil_data_soil_ph_in_range CHECK (soil_ph IS NULL OR soil_ph BETWEEN 0 AND 14),
    CONSTRAINT ck_soil_data_soil_moisture_in_range CHECK (soil_moisture IS NULL OR soil_moisture BETWEEN 0 AND 100),
    CONSTRAINT ck_soil_data_soil_temperature_in_range CHECK (soil_temperature IS NULL OR soil_temperature BETWEEN -20 AND 80),
    CONSTRAINT ck_soil_data_electrical_conductivity_in_range CHECK (electrical_conductivity IS NULL OR electrical_conductivity BETWEEN 0 AND 30),
    CONSTRAINT ck_soil_data_nitrogen_in_range CHECK (nitrogen IS NULL OR nitrogen BETWEEN 0 AND 2000),
    CONSTRAINT ck_soil_data_phosphorus_in_range CHECK (phosphorus IS NULL OR phosphorus BETWEEN 0 AND 2000),
    CONSTRAINT ck_soil_data_potassium_in_range CHECK (potassium IS NULL OR potassium BETWEEN 0 AND 5000),
    CONSTRAINT ck_soil_data_air_temperature_in_range CHECK (air_temperature IS NULL OR air_temperature BETWEEN -40 AND 60),
    CONSTRAINT ck_soil_data_air_humidity_in_range CHECK (air_humidity IS NULL OR air_humidity BETWEEN 0 AND 100)
) PARTITION BY RANGE (recorded_at);

SELECT farmxpert_rolling_partitions('soil_data');

-- The query every agent path runs: newest reading for this farm.
CREATE INDEX ix_soil_data_farm_id_recorded_at ON soil_data (farm_id, recorded_at DESC);
CREATE INDEX ix_soil_data_field_id_recorded_at ON soil_data (field_id, recorded_at DESC);
-- BRIN: a few KB instead of GB, and ideal for a column that grows in time order.
CREATE INDEX ix_soil_data_recorded_at_brin ON soil_data USING brin (recorded_at);
-- A retried upload must not double a reading.
CREATE UNIQUE INDEX uq_soil_data_farm_id_recorded_at_source
    ON soil_data (farm_id, recorded_at, source) WHERE device_id IS NULL;
CREATE UNIQUE INDEX uq_soil_data_device_recorded_at
    ON soil_data (device_id, recorded_at) WHERE device_id IS NOT NULL;

CREATE TABLE soil_analyses (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    reading_id          uuid        NOT NULL,
    reading_recorded_at timestamptz NOT NULL,
    farm_id             uuid        NOT NULL REFERENCES farms (id) ON DELETE CASCADE,
    agent_version       varchar(20) NOT NULL,
    health_score        double precision,
    health_status       varchar(20),
    summary             text,
    alerts              jsonb,
    fertilizers         jsonb,
    recommendations     jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    -- A foreign key into a partitioned table must name its whole key.
    CONSTRAINT fk_soil_analyses_reading_soil_data FOREIGN KEY (reading_id, reading_recorded_at)
        REFERENCES soil_data (id, recorded_at) ON DELETE CASCADE,
    CONSTRAINT ck_soil_analyses_score_in_range CHECK (health_score IS NULL OR health_score BETWEEN 0 AND 100)
);
CREATE INDEX ix_soil_analyses_reading ON soil_analyses (reading_id, reading_recorded_at);
CREATE INDEX ix_soil_analyses_farm_id_created_at ON soil_analyses (farm_id, created_at DESC);

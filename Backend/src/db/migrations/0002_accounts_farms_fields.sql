-- 0002 Users, crops, farms and fields: the spatial core.
--
-- Location is PostGIS geography, not two floats: distance in metres on the
-- globe, a GIST index for "farms near this mandi", and polygons for field
-- boundaries. latitude/longitude are GENERATED from the geography so existing
-- readers keep working and can never disagree with it.

CREATE TABLE users (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        varchar(120) NOT NULL,
    phone       varchar(16),
    language    varchar(12) NOT NULL DEFAULT 'en',
    deleted_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_users_name_not_blank CHECK (char_length(btrim(name)) > 0),
    CONSTRAINT ck_users_phone_looks_valid CHECK (phone IS NULL OR phone ~ '^[0-9+][0-9]{7,14}$')
);
-- A soft-deleted account must not hold its phone number hostage.
CREATE UNIQUE INDEX uq_users_phone_active ON users (phone)
    WHERE deleted_at IS NULL AND phone IS NOT NULL;

-- Reference data. The agents' configs are the authority for what they compute
-- with; this table carries identity and display data.
CREATE TABLE crops (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug              varchar(80) NOT NULL,
    name              varchar(80) NOT NULL,
    season            varchar(20),
    duration_days     integer,
    water_requirement varchar(20),
    soil_ph_min       double precision,
    soil_ph_max       double precision,
    npk_requirements  jsonb,
    climate_zone      varchar(50),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_crops_duration_plausible CHECK (duration_days IS NULL OR duration_days BETWEEN 30 AND 730),
    CONSTRAINT ck_crops_ph_range_ordered CHECK (soil_ph_min IS NULL OR soil_ph_max IS NULL OR soil_ph_max >= soil_ph_min),
    CONSTRAINT ck_crops_ph_in_range CHECK ((soil_ph_min IS NULL OR soil_ph_min BETWEEN 0 AND 14)
                                       AND (soil_ph_max IS NULL OR soil_ph_max BETWEEN 0 AND 14))
);
-- The lower-case name is the key agents use; two spellings of "Groundnut"
-- would silently split a farm's history in two.
CREATE UNIQUE INDEX uq_crops_slug ON crops (slug);

CREATE TABLE farms (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name          varchar(120),
    location      geography(POINT, 4326),
    latitude      double precision GENERATED ALWAYS AS (ST_Y(location::geometry)) STORED,
    longitude     double precision GENERATED ALWAYS AS (ST_X(location::geometry)) STORED,
    area_hectares numeric(10, 3),
    address       varchar(255),
    state         varchar(80),
    district      varchar(80),
    timezone      varchar(64) NOT NULL DEFAULT 'Asia/Kolkata',
    deleted_at    timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_farms_area_positive CHECK (area_hectares IS NULL OR area_hectares > 0),
    CONSTRAINT ck_farms_area_plausible CHECK (area_hectares IS NULL OR area_hectares < 100000)
);
CREATE INDEX ix_farms_location ON farms USING gist (location);
CREATE INDEX ix_farms_user_id_active ON farms (user_id, created_at DESC) WHERE deleted_at IS NULL;

-- A worked piece of a farm: one boundary, one crop, one calendar. Agents
-- reason at this level - groundnut in one plot and cotton in the next must
-- not share one soil reading and one irrigation plan.
CREATE TABLE fields (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    farm_id             uuid        NOT NULL REFERENCES farms (id) ON DELETE CASCADE,
    name                varchar(80) NOT NULL,
    boundary            geography(POLYGON, 4326),
    area_hectares       numeric(10, 3),
    soil_type           varchar(50),
    irrigation_method   varchar(30),
    crop_id             uuid        REFERENCES crops (id) ON DELETE SET NULL,
    crop_name           varchar(80),
    growth_stage        varchar(30),
    sown_on             date,
    expected_harvest_on date,
    deleted_at          timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_fields_farm_id_name UNIQUE (farm_id, name),
    CONSTRAINT ck_fields_area_positive CHECK (area_hectares IS NULL OR area_hectares > 0),
    CONSTRAINT ck_fields_harvest_after_sowing CHECK (
        sown_on IS NULL OR expected_harvest_on IS NULL OR expected_harvest_on >= sown_on)
);
CREATE INDEX ix_fields_boundary ON fields USING gist (boundary);
CREATE INDEX ix_fields_farm_id_active ON fields (farm_id) WHERE deleted_at IS NULL;

-- What a field grew, and what it returned: the honest test of past advice.
CREATE TABLE crop_history (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    farm_id           uuid        NOT NULL REFERENCES farms (id) ON DELETE CASCADE,
    field_id          uuid        REFERENCES fields (id) ON DELETE SET NULL,
    crop_id           uuid        REFERENCES crops (id) ON DELETE SET NULL,
    crop_name         varchar(80) NOT NULL,
    season            varchar(20),
    year              integer     NOT NULL,
    sown_on           date,
    harvested_on      date,
    yield_per_hectare numeric(10, 2),
    revenue           numeric(12, 2),
    cost              numeric(12, 2),
    notes             varchar(500),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_crop_history_season UNIQUE (field_id, crop_id, season, year),
    CONSTRAINT ck_crop_history_year_plausible CHECK (year BETWEEN 1990 AND 2100),
    CONSTRAINT ck_crop_history_yield_positive CHECK (yield_per_hectare IS NULL OR yield_per_hectare >= 0),
    CONSTRAINT ck_crop_history_harvest_after_sowing CHECK (
        sown_on IS NULL OR harvested_on IS NULL OR harvested_on >= sown_on)
);
CREATE INDEX ix_crop_history_farm_id_year ON crop_history (farm_id, year DESC);

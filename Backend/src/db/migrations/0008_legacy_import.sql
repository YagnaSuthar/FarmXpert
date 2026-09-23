-- 0008 Carry rows from the old Python schema's tables (renamed *_legacy by
-- 0001) into the new ones. Every block is a no-op on a fresh database. The
-- legacy tables are left in place for inspection; drop them by hand once the
-- import has been checked.

DO $$
BEGIN
    IF to_regclass('farms_legacy') IS NULL THEN RETURN; END IF;

    INSERT INTO users (id, name)
    SELECT DISTINCT l.user_id, 'Recovered account'
      FROM farms_legacy l
     WHERE l.user_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = l.user_id);

    INSERT INTO users (id, name)
    SELECT '00000000-0000-0000-0000-000000000001', 'Unassigned farms'
     WHERE EXISTS (SELECT 1 FROM farms_legacy WHERE user_id IS NULL)
       AND NOT EXISTS (SELECT 1 FROM users WHERE id = '00000000-0000-0000-0000-000000000001');

    INSERT INTO farms (id, user_id, area_hectares, location, created_at)
    SELECT l.id,
           COALESCE(l.user_id, '00000000-0000-0000-0000-000000000001'),
           -- The old column was acres.
           CASE WHEN l.farm_size_acres > 0
                THEN ROUND((l.farm_size_acres * 0.404686)::numeric, 3) END,
           CASE WHEN l.latitude BETWEEN -90 AND 90 AND l.longitude BETWEEN -180 AND 180
                THEN ST_SetSRID(ST_MakePoint(l.longitude, l.latitude), 4326)::geography END,
           COALESCE(l.created_at, now())
      FROM farms_legacy l
    ON CONFLICT (id) DO NOTHING;
END $$;

-- Out-of-range values become NULL rather than costing the row: one broken
-- probe channel must not lose the other readings.
DO $$
DECLARE
    oldest timestamptz;
BEGIN
    IF to_regclass('soil_data_legacy') IS NULL THEN RETURN; END IF;

    -- Real monthly partitions for the old months, not the DEFAULT catch-all,
    -- so the lifecycle job can archive them like any other month.
    SELECT min(recorded_at) INTO oldest FROM soil_data_legacy;
    IF oldest IS NOT NULL THEN
        PERFORM farmxpert_create_monthly_partitions('soil_data', oldest::date, now()::date);
    END IF;

    INSERT INTO soil_data (
        farm_id, recorded_at, source, soil_moisture, soil_temperature,
        soil_ph, electrical_conductivity, nitrogen, phosphorus, potassium,
        air_temperature, air_humidity, soil_type, crop_type, rainfall,
        irrigation_type, irrigation_amount, fertilizer_type, fertilizer_amount)
    SELECT l.farm_id, COALESCE(l.recorded_at, now()), 'sensor',
           CASE WHEN l.soil_moisture BETWEEN 0 AND 100 THEN l.soil_moisture END,
           CASE WHEN l.soil_temperature BETWEEN -20 AND 80 THEN l.soil_temperature END,
           CASE WHEN l.soil_ph BETWEEN 0 AND 14 THEN l.soil_ph END,
           CASE WHEN l.electrical_conductivity BETWEEN 0 AND 30 THEN l.electrical_conductivity END,
           CASE WHEN l.nitrogen BETWEEN 0 AND 2000 THEN l.nitrogen END,
           CASE WHEN l.phosphorus BETWEEN 0 AND 2000 THEN l.phosphorus END,
           CASE WHEN l.potassium BETWEEN 0 AND 5000 THEN l.potassium END,
           CASE WHEN l.air_temperature BETWEEN -40 AND 60 THEN l.air_temperature END,
           CASE WHEN l.air_humidity BETWEEN 0 AND 100 THEN l.air_humidity END,
           l.soil_type, l.crop_type, l.rainfall, l.irrigation_type,
           l.irrigation_amount, l.fertilizer_type, l.fertilizer_amount
      FROM soil_data_legacy l
     WHERE l.farm_id IS NOT NULL
       AND EXISTS (SELECT 1 FROM farms f WHERE f.id = l.farm_id)
    ON CONFLICT DO NOTHING;
END $$;

-- Parse the old text dates and collapse the duplicates the missing unique key
-- let accumulate (keeping the most recent fetch of each observation).
DO $$
BEGIN
    IF to_regclass('mandi_price_data_legacy') IS NULL THEN RETURN; END IF;

    INSERT INTO mandi_price_data (
        commodity, market, state, district, arrival_date,
        min_price, max_price, modal_price, variety, grade, source, created_at)
    SELECT DISTINCT ON (l.commodity, l.market, d.parsed, COALESCE(l.variety, ''), COALESCE(l.grade, ''))
           l.commodity, l.market, l.state, l.district, d.parsed,
           -- The old ingest wrote 0.0 for a missing price; that is not a price.
           NULLIF(l.min_price, 0), NULLIF(l.max_price, 0), NULLIF(l.modal_price, 0),
           COALESCE(l.variety, ''), COALESCE(l.grade, ''),
           COALESCE(l.source, 'AGMARKNET'), COALESCE(l.recorded_at, now())
      FROM mandi_price_data_legacy l
      CROSS JOIN LATERAL (
          SELECT CASE
              WHEN l.arrival_date ~ '^\d{4}-\d{2}-\d{2}$' THEN l.arrival_date::date
              WHEN l.arrival_date ~ '^\d{2}/\d{2}/\d{4}$' THEN to_date(l.arrival_date, 'DD/MM/YYYY')
              ELSE COALESCE(l.recorded_at::date, CURRENT_DATE)
          END AS parsed) d
     WHERE l.commodity IS NOT NULL AND l.market IS NOT NULL
       -- Rows the new checks would reject (e.g. max below min) stay behind.
       AND (NULLIF(l.min_price, 0) IS NULL OR NULLIF(l.max_price, 0) IS NULL
            OR NULLIF(l.max_price, 0) >= NULLIF(l.min_price, 0))
       AND (NULLIF(l.modal_price, 0) IS NULL OR NULLIF(l.min_price, 0) IS NULL
            OR NULLIF(l.max_price, 0) IS NULL
            OR NULLIF(l.modal_price, 0) BETWEEN NULLIF(l.min_price, 0) AND NULLIF(l.max_price, 0))
     ORDER BY l.commodity, l.market, d.parsed, COALESCE(l.variety, ''), COALESCE(l.grade, ''),
              l.recorded_at DESC NULLS LAST
    ON CONFLICT ON CONSTRAINT uq_mandi_price_data_observation DO NOTHING;
END $$;

-- Only the newest token per farm stays active; older ones arrive revoked, so
-- the one-active-token index holds and the history is not thrown away.
DO $$
BEGIN
    IF to_regclass('blynk_tokens_legacy') IS NULL THEN RETURN; END IF;

    INSERT INTO blynk_tokens (farm_id, token, is_active, revoked_at, created_at)
    SELECT r.farm_id, r.token,
           r.rn = 1 AND COALESCE(r.is_active, true),
           CASE WHEN r.rn > 1 OR NOT COALESCE(r.is_active, true) THEN now() END,
           COALESCE(r.created_at, now())
      FROM (SELECT l.*, row_number() OVER (
                       PARTITION BY l.farm_id
                       ORDER BY COALESCE(l.is_active, true) DESC, l.created_at DESC NULLS LAST) AS rn
              FROM blynk_tokens_legacy l) r
     WHERE r.farm_id IS NOT NULL AND char_length(r.token) >= 8
       AND EXISTS (SELECT 1 FROM farms f WHERE f.id = r.farm_id)
    ON CONFLICT (token) DO NOTHING;
END $$;

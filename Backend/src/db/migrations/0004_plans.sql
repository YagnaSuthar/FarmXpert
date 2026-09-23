-- 0004 The records a farmer acts on: crop choices, irrigation plans, work plans.
--
-- These existed nowhere before - every plan was computed, shown once, and
-- lost. That made it impossible to tell a farmer what they were advised last
-- week, or to measure whether the advice worked.

CREATE TABLE crop_recommendations (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    farm_id         uuid        NOT NULL REFERENCES farms (id) ON DELETE CASCADE,
    field_id        uuid        REFERENCES fields (id) ON DELETE SET NULL,
    request_id      varchar(64),
    input_data      jsonb,
    recommendations jsonb,
    top_crop        varchar(80),
    confidence      double precision,
    agent_version   varchar(20) NOT NULL,
    model_version   varchar(40),
    season          varchar(20),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_crop_recommendations_confidence_in_range CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1)
);
CREATE INDEX ix_crop_recommendations_farm_id_created_at ON crop_recommendations (farm_id, created_at DESC);

CREATE TABLE irrigation_plans (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    farm_id          uuid        NOT NULL REFERENCES farms (id) ON DELETE CASCADE,
    field_id         uuid        REFERENCES fields (id) ON DELETE SET NULL,
    request_id       varchar(64),
    plan_date        date        NOT NULL,
    crop             varchar(80),
    growth_stage     varchar(30),
    decision         varchar(40) NOT NULL,
    water_depth_mm   numeric(6, 2),
    duration_hours   numeric(5, 2),
    method           varchar(30),
    plan             jsonb,
    agent_version    varchar(20) NOT NULL,
    status           varchar(20) NOT NULL DEFAULT 'planned',
    -- What the farmer actually applied closes the loop: advice nobody records
    -- acting on cannot be evaluated.
    applied_at       timestamptz,
    applied_depth_mm numeric(6, 2),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_irrigation_plans_depth_plausible CHECK (water_depth_mm IS NULL OR water_depth_mm BETWEEN 0 AND 500),
    CONSTRAINT ck_irrigation_plans_applied_depth_positive CHECK (applied_depth_mm IS NULL OR applied_depth_mm >= 0),
    CONSTRAINT ck_irrigation_plans_status_known CHECK (status IN ('planned', 'applied', 'skipped', 'superseded'))
);
CREATE INDEX ix_irrigation_plans_farm_id_plan_date ON irrigation_plans (farm_id, plan_date DESC);
CREATE INDEX ix_irrigation_plans_field_id_plan_date ON irrigation_plans (field_id, plan_date DESC);

CREATE TABLE task_plans (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    farm_id       uuid        NOT NULL REFERENCES farms (id) ON DELETE CASCADE,
    field_id      uuid        REFERENCES fields (id) ON DELETE SET NULL,
    request_id    varchar(64),
    plan_date     date        NOT NULL,
    horizon_days  integer     NOT NULL DEFAULT 3,
    headline      text,
    summary       text,
    -- The plan header. Its tasks live as rows in scheduled_tasks, not here too.
    plan          jsonb,
    agent_version varchar(20) NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_task_plans_farm_id_plan_date ON task_plans (farm_id, plan_date DESC);

-- One job on one day - the row a farmer ticks off, skips or does late.
CREATE TABLE scheduled_tasks (
    id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_plan_id         uuid        NOT NULL REFERENCES task_plans (id) ON DELETE CASCADE,
    farm_id              uuid        NOT NULL REFERENCES farms (id) ON DELETE CASCADE,
    field_id             uuid        REFERENCES fields (id) ON DELETE SET NULL,
    title                varchar(200) NOT NULL,
    category             varchar(40) NOT NULL,
    priority             varchar(20) NOT NULL,
    status               varchar(20) NOT NULL DEFAULT 'scheduled',
    scheduled_date       date,
    scheduled_start_time varchar(5),
    duration_minutes     integer     NOT NULL DEFAULT 60,
    why_now              text,
    detail               jsonb,
    completed_at         timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_scheduled_tasks_status_known CHECK (status IN ('scheduled', 'delayed', 'skipped', 'done', 'cancelled')),
    CONSTRAINT ck_scheduled_tasks_priority_known CHECK (priority IN ('critical', 'high', 'medium', 'low', 'deferred')),
    CONSTRAINT ck_scheduled_tasks_duration_positive CHECK (duration_minutes > 0)
);
CREATE INDEX ix_scheduled_tasks_task_plan_id ON scheduled_tasks (task_plan_id);
CREATE INDEX ix_scheduled_tasks_farm_id_scheduled_date ON scheduled_tasks (farm_id, scheduled_date);
-- "Today's open jobs": the home screen, served without touching done work.
CREATE INDEX ix_scheduled_tasks_open ON scheduled_tasks (farm_id, scheduled_date)
    WHERE status IN ('scheduled', 'delayed');

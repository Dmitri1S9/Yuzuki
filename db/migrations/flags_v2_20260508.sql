-- Migration: flags v2 (2026-05-08)
-- Removes: is_leader, is_mentor, is_villain, is_antihero, is_duty_driven
-- Adds:    has_humor (personality), is_muscular / has_distinctive_feature / is_well_groomed (appearance)
-- Unchanged: is_strategist

BEGIN;

-- universes (JSONB aggregate columns)
ALTER TABLE universes
    DROP COLUMN IF EXISTS is_leader,
    DROP COLUMN IF EXISTS is_mentor,
    DROP COLUMN IF EXISTS is_villain,
    DROP COLUMN IF EXISTS is_antihero,
    DROP COLUMN IF EXISTS is_duty_driven,
    ADD COLUMN has_humor               JSONB,
    ADD COLUMN is_muscular             JSONB,
    ADD COLUMN has_distinctive_feature JSONB,
    ADD COLUMN is_well_groomed         JSONB;

-- characters (INT position columns)
ALTER TABLE characters
    DROP COLUMN IF EXISTS is_leader,
    DROP COLUMN IF EXISTS is_mentor,
    DROP COLUMN IF EXISTS is_villain,
    DROP COLUMN IF EXISTS is_antihero,
    DROP COLUMN IF EXISTS is_duty_driven,
    ADD COLUMN has_humor               INT,
    ADD COLUMN is_muscular             INT,
    ADD COLUMN has_distinctive_feature INT,
    ADD COLUMN is_well_groomed         INT;

COMMIT;

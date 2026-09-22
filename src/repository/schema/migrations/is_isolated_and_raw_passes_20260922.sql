-- Migration: is_isolated column + raw_passes cache table (2026-09-22)
-- is_isolated: stage 1's "confirmed loner" signal (roster.py's
-- found["isolates"] >= ROSTER_MIN_PASSES) used to live only in
-- stage1_cast_{SLUG}.json, never in Postgres — needed here now that
-- relations/features/graph read the roster from the database instead of
-- that file.
-- raw_passes: replaces pass{N}_{SLUG}.csv — the per-character/per-param raw
-- Gemini scores features/steps/collection.py caches to avoid re-paying for a
-- debug rerun. One row per (universe, pass, param, character).
BEGIN;

ALTER TABLE characters ADD COLUMN is_isolated BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE raw_passes (
    universe_id BIGINT NOT NULL REFERENCES universes(id) ON DELETE CASCADE,
    pass_number INT NOT NULL,
    param       TEXT NOT NULL,
    name        TEXT NOT NULL,
    score       DOUBLE PRECISION,
    PRIMARY KEY (universe_id, pass_number, param, name)
);

COMMIT;

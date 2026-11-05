-- Migration: relations (2026-09-05)
-- Adds storage for the new relation_task (for/against/want/with), run as
-- 3 independent passes per type. Directed types (for, want) use
-- source/target. Symmetric types (against, with) use members (JSONB,
-- 2 = pair, 3+ = clique). pass_number tags which of the 3 runs produced
-- the row.

BEGIN;

CREATE TABLE relations (
    id            BIGSERIAL PRIMARY KEY,
    universe_id   BIGINT NOT NULL REFERENCES universes(id) ON DELETE CASCADE,
    relation_type VARCHAR(10) NOT NULL,  -- for / against / want / with
    source        TEXT,                  -- directed only
    target        TEXT,                  -- directed only
    members       JSONB,                 -- symmetric only: ["name1", "name2", ...]
    pass_number   INT
);

CREATE INDEX idx_relations_universe ON relations(universe_id);

COMMIT;

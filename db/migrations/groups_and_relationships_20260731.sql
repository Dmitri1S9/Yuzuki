-- Migration: groups + relationship graph (2026-07-31)
-- Adds storage for the new group_task (small/medium/large/isolates) and a
-- stub relationship graph (empty adjacency matrix, no relationship logic yet).

BEGIN;

CREATE TABLE groups (
    id          BIGSERIAL PRIMARY KEY,
    universe_id BIGINT NOT NULL REFERENCES universes(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    group_type  VARCHAR(10) NOT NULL,  -- small / medium / large / isolated
    leader      TEXT,
    members     JSONB NOT NULL         -- ["name1", "name2", ...]
);

CREATE INDEX idx_groups_universe ON groups(universe_id);

CREATE TABLE relationship_graphs (
    id          BIGSERIAL PRIMARY KEY,
    universe_id BIGINT NOT NULL UNIQUE REFERENCES universes(id) ON DELETE CASCADE,
    characters  JSONB NOT NULL,
    matrix      JSONB NOT NULL
);

COMMIT;

-- groups/relations were designed for raw per-pass storage (pass_number INT,
-- one row per single-pass mention) — that predates this session's rework:
-- overlap-coefficient dedup across passes (stage1_cast.py), medium-scoped +
-- general_pool + star reduction (stage3_relations.py). Neither table can
-- currently hold what those stages actually produce. This migration adds
-- the columns for the merged/consolidated shape; it does not touch or
-- remove pass_number (left nullable, simply unused going forward).

ALTER TABLE groups
    ADD COLUMN name_variants JSONB,  -- distinct raw names this cluster was called across passes
    ADD COLUMN passes        JSONB;  -- which raw pass numbers (e.g. [1,3]) this cluster survived on

ALTER TABLE relations
    ADD COLUMN source_level  TEXT,   -- 'medium:<group name>' | 'general_pool' — see PIPELINE.md Этап 3
    ADD COLUMN count         INT;    -- passes *within that one level* that confirmed this edge —
                                      -- never comparable or summed across two different source_level rows

-- New: allied/rival pairs between groups (large+medium combined) — a
-- separate table, deliberately never merged into character-level `relations`.
-- See PIPELINE.md Этап 3 → "между группами".
CREATE TABLE group_relations (
    id          BIGSERIAL PRIMARY KEY,
    universe_id BIGINT NOT NULL REFERENCES universes(id) ON DELETE CASCADE,
    group_a     TEXT NOT NULL,
    group_b     TEXT NOT NULL,
    kind        VARCHAR(10) NOT NULL  -- 'allied' | 'rival'
);

CREATE INDEX idx_group_relations_universe ON group_relations(universe_id);

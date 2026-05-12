-- ============================================================
-- Yuzuki — flat schema (2 tables)
-- ============================================================

DROP TABLE IF EXISTS characters CASCADE;
DROP TABLE IF EXISTS universes CASCADE;

-- ---------- universes ----------
-- Each parameter column = JSONB array [count per segment]
-- Ordinal: [count_T1, count_T2, count_T3, ...]
-- Flags:   [before_T0, between_T0_T1, after_T1, unknown]
CREATE TABLE universes (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    arc             TEXT NOT NULL DEFAULT '',
    character_count INT  DEFAULT 0,
    UNIQUE (name, arc),

    -- ordinal
    combat_potential    JSONB,
    intellect           JSONB,
    authority_scope     JSONB,
    loyalty_command      JSONB,
    social_impact       JSONB,
    wealth              JSONB,

    -- flags
    manipulative        JSONB,
    honest              JSONB,
    impulsive           JSONB,
    secretive           JSONB,
    self_sacrificing    JSONB,
    adaptable           JSONB,
    loyal               JSONB,
    empathetic          JSONB,
    cruel               JSONB,
    arrogant            JSONB,
    competitive         JSONB,
    ruthless            JSONB,

    is_strategist       JSONB,
    has_humor           JSONB,

    is_physically_attractive  JSONB,
    is_intimidating           JSONB,
    is_muscular               JSONB,
    has_distinctive_feature   JSONB,
    is_well_groomed           JSONB,

    goal_power          JSONB,
    goal_love           JSONB,
    goal_knowledge      JSONB,
    goal_revenge        JSONB,
    goal_survival       JSONB,
    goal_duty           JSONB,
    goal_freedom        JSONB,
    goal_recognition    JSONB,
    goal_protection     JSONB,

    military            JSONB,
    politics            JSONB,
    science             JSONB,
    art                 JSONB,
    education           JSONB,
    crime               JSONB,
    commerce            JSONB,

    has_magic           JSONB,
    has_tragic_past     JSONB,
    is_strong_willed    JSONB,
    is_provocative      JSONB,
    is_loner            JSONB,
    is_unstable         JSONB,
    is_fanatical        JSONB,

    is_idealist         JSONB,
    is_nihilist         JSONB,
    is_pragmatist       JSONB,
    is_hedonist         JSONB,
    is_machiavellian    JSONB,
    is_revolutionary    JSONB,
    is_fatalist         JSONB,

    has_physical_weakness       JSONB,
    has_psychological_weakness  JSONB,

    -- profile aggregates (JSONB: {"male": N, "female": N, ...} etc.)
    gender_counts   JSONB,
    species_counts  JSONB
);

-- ---------- characters ----------
-- All parameter columns = INT (position in sorted list, NULL = unknown)
CREATE TABLE characters (
    id          BIGSERIAL PRIMARY KEY,
    universe_id BIGINT NOT NULL REFERENCES universes(id) ON DELETE CASCADE,
    name        TEXT   NOT NULL,
    UNIQUE (universe_id, name),

    -- profile
    body_age    VARCHAR(10),
    soul_age    VARCHAR(10),
    gender      VARCHAR(10),
    species     VARCHAR(50),

    -- ordinal (position in sorted list)
    combat_potential    INT,
    intellect           INT,
    authority_scope     INT,
    loyalty_command      INT,
    social_impact       INT,
    wealth              INT,

    -- flags (position in sorted list)
    manipulative        INT,
    honest              INT,
    impulsive           INT,
    secretive           INT,
    self_sacrificing    INT,
    adaptable           INT,
    loyal               INT,
    empathetic          INT,
    cruel               INT,
    arrogant            INT,
    competitive         INT,
    ruthless            INT,

    is_strategist       INT,
    has_humor           INT,

    is_physically_attractive  INT,
    is_intimidating           INT,
    is_muscular               INT,
    has_distinctive_feature   INT,
    is_well_groomed           INT,

    goal_power          INT,
    goal_love           INT,
    goal_knowledge      INT,
    goal_revenge        INT,
    goal_survival       INT,
    goal_duty           INT,
    goal_freedom        INT,
    goal_recognition    INT,
    goal_protection     INT,

    military            INT,
    politics            INT,
    science             INT,
    art                 INT,
    education           INT,
    crime               INT,
    commerce            INT,

    has_magic           INT,
    has_tragic_past     INT,
    is_strong_willed    INT,
    is_provocative      INT,
    is_loner            INT,
    is_unstable         INT,
    is_fanatical        INT,

    is_idealist         INT,
    is_nihilist         INT,
    is_pragmatist       INT,
    is_hedonist         INT,
    is_machiavellian    INT,
    is_revolutionary    INT,
    is_fatalist         INT,

    has_physical_weakness       INT,
    has_psychological_weakness  INT
);

CREATE INDEX idx_characters_universe ON characters(universe_id);

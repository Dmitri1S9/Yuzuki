-- Migration: character aliases (2026-09-07)
-- Stores other names a character is known by (hero name, codename, title,
-- real name), from stage 1 alias resolution. NULL/absent = single name only.

BEGIN;

ALTER TABLE characters ADD COLUMN aliases JSONB;

COMMIT;

-- Migration: character images (2026-09-22)
-- Stores a stage 1 web-search result per character: a candidate portrait
-- image (linked, not re-hosted) and how many search hits actually co-occur
-- with the universe name (near-zero = likely fabricated).
BEGIN;
ALTER TABLE characters ADD COLUMN image_url TEXT;
ALTER TABLE characters ADD COLUMN existence_hits INT;
COMMIT;

-- Migration: character portrait bytes in Postgres (2026-09-28)
-- Replaces filesystem-hosted portraits (media/characters/*.jpg) with an
-- in-DB blob, so the image is part of the same row/backup/restore unit as
-- the rest of the character instead of a file tree that can drift out of
-- sync with the database. image_url/existence_hits are left in place —
-- existence_hits is still real data; image_url becomes dead once every
-- reader has moved to the new /portrait route.
BEGIN;
ALTER TABLE characters ADD COLUMN image_bytes BYTEA;
ALTER TABLE characters ADD COLUMN image_content_type TEXT;
COMMIT;

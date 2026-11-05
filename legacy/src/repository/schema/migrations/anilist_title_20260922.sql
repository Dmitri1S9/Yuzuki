-- Migration: AniList search title override (2026-09-22)
-- The exact AniList media title to search for this universe, when an
-- arc doesn't map onto the same title as the universe's own display name
-- (a later season/movie can have an unrelated-looking title). NULL/absent
-- = search with the universe's own name, the common case.
BEGIN;
ALTER TABLE universes ADD COLUMN anilist_title TEXT;
COMMIT;

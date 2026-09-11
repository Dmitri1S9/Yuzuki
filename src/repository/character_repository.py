"""CharacterRepository — search/save for individual characters.

Profile fields (body_age/soul_age/gender/species) are read from the real
`characters` columns, but nothing in the live pipeline writes them yet —
profile collection was only ever wired through the deleted Celery path.
Ordinal/flag values are wired up (Character.get_flag/get_ordinal, the
parameter registry) but always come back empty too: stage2 (ordinal/flag
consensus) results aren't persisted to the database yet. Both are known
gaps, unchanged by this reorg (see ARCHITECTURE.md). find_characters()
already filters correctly against all three once the data exists; it just
has nothing to match against right now.
"""
import logging

from psycopg2.extras import Json

from src.domain.character import Character
from src.domain.parameters import FLAG_PARAMS, ORDINAL_PARAMS, PROFILE_PARAMS
from src.repository.connection import read_only, transactional

log = logging.getLogger(__name__)

_PROFILE_COLUMNS = tuple(PROFILE_PARAMS)  # ("body_age", "soul_age", "gender", "species")


def _character_from_row(universe_id: int, name: str, aliases, *profile_values) -> Character:
    profile = dict(zip(_PROFILE_COLUMNS, profile_values))
    return Character(name=name, universe_id=universe_id, aliases=aliases or [], profile=profile)


def _load_roster(conn, universe_id: int) -> list[Character]:
    cols = ", ".join(_PROFILE_COLUMNS)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT name, aliases, {cols} FROM characters WHERE universe_id = %s ORDER BY name",
            (universe_id,),
        )
        rows = cur.fetchall()
    return [_character_from_row(universe_id, name, aliases, *profile_values)
            for name, aliases, *profile_values in rows]


class CharacterRepository:

    @read_only
    def get_character(self, conn, universe_id: int, name: str) -> Character | None:
        cols = ", ".join(_PROFILE_COLUMNS)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT name, aliases, {cols} FROM characters WHERE universe_id = %s AND name = %s",
                (universe_id, name),
            )
            row = cur.fetchone()
        return None if row is None else _character_from_row(universe_id, row[0], row[1], *row[2:])

    @read_only
    def get_characters(self, conn, universe_id: int, names: list[str]) -> list[Character]:
        """Search by one or several names at once."""
        if not names:
            return []
        cols = ", ".join(_PROFILE_COLUMNS)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT name, aliases, {cols} FROM characters WHERE universe_id = %s AND name = ANY(%s)",
                (universe_id, names),
            )
            rows = cur.fetchall()
        return [_character_from_row(universe_id, name, aliases, *profile_values)
                for name, aliases, *profile_values in rows]

    @read_only
    def find_characters(self, conn, universe_id: int, **filters) -> list[Character]:
        """Sample the roster by parameter, e.g. find_characters(uid, cruel=True)
        or find_characters(uid, gender="female") — any name known to
        Character.help() works, dispatched through Character.__getitem__."""
        roster = _load_roster(conn, universe_id)
        for key, value in filters.items():
            if key not in PROFILE_PARAMS and key not in FLAG_PARAMS and key not in ORDINAL_PARAMS:
                raise ValueError(f"unknown filter: {key!r}")
            roster = [c for c in roster if c[key] == value]
        return roster

    @transactional
    def save_character_aliases(self, conn, universe_id: int, name: str, aliases: list[str]) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE characters SET aliases = %s WHERE universe_id = %s AND name = %s",
                (Json(aliases) if aliases else None, universe_id, name),
            )
        log.info("saved %d alias(es) for %r (universe %d)", len(aliases), name, universe_id)

import logging

from src.domain.universe import Universe
from src.repository.character_repository import _load_roster
from src.repository.connection import read_only, transactional
from src.repository.group_repository import _load_groups

log = logging.getLogger(__name__)


class UniverseRepository:

    @transactional
    def create_universe(self, conn, name: str, characters: list[str], arc: str | None = None) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO universes (name, arc, character_count)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (name, arc) DO UPDATE SET character_count = EXCLUDED.character_count
                   RETURNING id""",
                (name, arc or "", len(characters)),
            )
            uid = cur.fetchone()[0]
            for char_name in characters:
                cur.execute(
                    """INSERT INTO characters (universe_id, name)
                       VALUES (%s, %s)
                       ON CONFLICT (universe_id, name) DO NOTHING""",
                    (uid, char_name),
                )
        log.info("universe %r (%r) -> id=%d, %d characters", name, arc, uid, len(characters))
        return uid

    @read_only
    def get_universe(self, conn, name: str, arc: str | None = None) -> Universe | None:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM universes WHERE name = %s AND arc = %s", (name, arc or ""))
            row = cur.fetchone()
        if row is None:
            return None
        universe_id = row[0]
        roster = _load_roster(conn, universe_id)
        groups = _load_groups(conn, universe_id)
        return Universe(universe_id, name, arc, roster=roster, groups=groups)

    @read_only
    def get_universe_by_id(self, conn, universe_id: int) -> Universe | None:
        with conn.cursor() as cur:
            cur.execute("SELECT name, arc FROM universes WHERE id = %s", (universe_id,))
            row = cur.fetchone()
        if row is None:
            return None
        name, arc = row
        roster = _load_roster(conn, universe_id)
        groups = _load_groups(conn, universe_id)
        return Universe(universe_id, name, arc or None, roster=roster, groups=groups)

    @read_only
    def list_universes(self, conn) -> list[Universe]:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, arc FROM universes ORDER BY name, arc")
            rows = cur.fetchall()
        return [Universe(uid, name, arc or None) for uid, name, arc in rows]

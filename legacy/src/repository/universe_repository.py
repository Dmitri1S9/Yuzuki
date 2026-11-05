from src.domain.universe import Universe
from src.repository.character_repository import _load_roster
from src.repository.connection import read_only, transactional
from src.repository.group_repository import _load_groups
from src.shared.decorators import logged


class UniverseRepository:

    @logged(lambda uid, self, name, characters, arc=None, anilist_title=None:
            f"universe {name!r} ({arc!r}) -> id={uid}, {len(characters)} characters")
    @transactional
    def create_universe(self, conn, name: str, characters: list[str], arc: str | None = None,
                         anilist_title: str | None = None) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO universes (name, arc, character_count, anilist_title)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (name, arc) DO UPDATE SET character_count = EXCLUDED.character_count,
                       anilist_title = COALESCE(EXCLUDED.anilist_title, universes.anilist_title)
                   RETURNING id""",
                (name, arc or "", len(characters), anilist_title),
            )
            uid = cur.fetchone()[0]
            for char_name in characters:
                cur.execute(
                    """INSERT INTO characters (universe_id, name)
                       VALUES (%s, %s)
                       ON CONFLICT (universe_id, name) DO NOTHING""",
                    (uid, char_name),
                )
        return uid

    @read_only
    def get_universe(self, conn, name: str, arc: str | None = None) -> Universe | None:
        with conn.cursor() as cur:
            cur.execute("SELECT id, anilist_title FROM universes WHERE name = %s AND arc = %s", (name, arc or ""))
            row = cur.fetchone()
        if row is None:
            return None
        universe_id, anilist_title = row
        roster = _load_roster(conn, universe_id)
        groups = _load_groups(conn, universe_id)
        return Universe(universe_id, name, arc, roster=roster, groups=groups, anilist_title=anilist_title)

    @read_only
    def get_universe_by_id(self, conn, universe_id: int) -> Universe | None:
        with conn.cursor() as cur:
            cur.execute("SELECT name, arc, anilist_title FROM universes WHERE id = %s", (universe_id,))
            row = cur.fetchone()
        if row is None:
            return None
        name, arc, anilist_title = row
        roster = _load_roster(conn, universe_id)
        groups = _load_groups(conn, universe_id)
        return Universe(universe_id, name, arc or None, roster=roster, groups=groups,
                         anilist_title=anilist_title)

    @read_only
    def list_universes(self, conn) -> list[Universe]:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, arc, anilist_title FROM universes ORDER BY name, arc")
            rows = cur.fetchall()
        return [Universe(uid, name, arc or None, anilist_title=anilist_title)
                for uid, name, arc, anilist_title in rows]

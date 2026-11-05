"""CharacterRepository — search/save for individual characters.

Profile fields (body_age/soul_age/gender/species) are read from the real
`characters` columns, but nothing in the live pipeline writes them yet —
profile collection was only ever wired through the deleted Celery path.
Ordinal/flag columns (one INT per parameter, position in the consensus
sort order, NULL = unknown/unconfirmed) are now loaded here too and
written via save_feature_position — the "Observe Beauty" ranking view is
the first real writer, see src/api/routes/confirm.py.
"""
import psycopg2
from psycopg2.extras import Json

from src.domain.character import Character
from src.domain.parameters import FLAG_PARAMS, ORDINAL_PARAMS, PROFILE_PARAMS
from src.infra.exceptions import CharacterException
from src.repository.connection import read_only, transactional, validate_column
from src.shared.decorators import logged

_PROFILE_COLUMNS = tuple(PROFILE_PARAMS)               # ("body_age", "soul_age", "gender", "species")
_FEATURE_COLUMNS = tuple(ORDINAL_PARAMS) + tuple(FLAG_PARAMS)  # one INT column per ordinal/flag
_ALL_COLUMNS = _PROFILE_COLUMNS + _FEATURE_COLUMNS


def _character_from_row(universe_id: int, name: str, aliases, has_portrait, existence_hits,
                         is_isolated, *values) -> Character:
    profile = dict(zip(_PROFILE_COLUMNS, values))
    features = dict(zip(_FEATURE_COLUMNS, values[len(_PROFILE_COLUMNS):]))
    ordinals = {k: v for k, v in features.items() if k in ORDINAL_PARAMS}
    flags = {k: v for k, v in features.items() if k in FLAG_PARAMS}
    return Character(name=name, universe_id=universe_id, aliases=aliases or [],
                      profile=profile, ordinals=ordinals, flags=flags,
                      has_portrait=has_portrait, existence_hits=existence_hits,
                      is_isolated=is_isolated)


def _load_roster(conn, universe_id: int) -> list[Character]:
    cols = ", ".join(_ALL_COLUMNS)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT name, aliases, (image_bytes IS NOT NULL) AS has_portrait, existence_hits, is_isolated, {cols} "
            f"FROM characters WHERE universe_id = %s ORDER BY name",
            (universe_id,),
        )
        rows = cur.fetchall()
    return [_character_from_row(universe_id, *row) for row in rows]


class CharacterRepository:

    @read_only
    def get_character(self, conn, universe_id: int, name: str) -> Character | None:
        cols = ", ".join(_ALL_COLUMNS)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT name, aliases, (image_bytes IS NOT NULL) AS has_portrait, existence_hits, is_isolated, {cols} "
                f"FROM characters WHERE universe_id = %s AND name = %s",
                (universe_id, name),
            )
            row = cur.fetchone()
        return None if row is None else _character_from_row(universe_id, *row)

    def get_character_or_raise(self, universe_id: int, name: str) -> Character:
        """Like get_character, but raises instead of returning None — the
        accessor routes should use when a missing character is a client
        error (404), not a value to check for by hand."""
        character = self.get_character(universe_id, name)
        if character is None:
            raise CharacterException(universe_id, name)
        return character

    @read_only
    def get_characters(self, conn, universe_id: int, names: list[str]) -> list[Character]:
        """Search by one or several names at once."""
        if not names:
            return []
        cols = ", ".join(_ALL_COLUMNS)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT name, aliases, (image_bytes IS NOT NULL) AS has_portrait, existence_hits, is_isolated, {cols} "
                f"FROM characters WHERE universe_id = %s AND name = ANY(%s)",
                (universe_id, names),
            )
            rows = cur.fetchall()
        return [_character_from_row(universe_id, *row) for row in rows]

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

    @logged(lambda _, self, universe_id, name, aliases:
            f"saved {len(aliases)} alias(es) for {name!r} (universe {universe_id})")
    @transactional
    def save_character_aliases(self, conn, universe_id: int, name: str, aliases: list[str]) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE characters SET aliases = %s WHERE universe_id = %s AND name = %s",
                (Json(aliases) if aliases else None, universe_id, name),
            )

    @transactional
    def save_character_isolation(self, conn, universe_id: int, name: str, is_isolated: bool) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE characters SET is_isolated = %s WHERE universe_id = %s AND name = %s",
                (is_isolated, universe_id, name),
            )

    @logged(lambda removed, self, universe_id, names:
            f"removed {len(removed)} character(s) no longer in the confirmed roster for universe {universe_id}: {removed}"
            if removed else None)
    @transactional
    def sync_roster(self, conn, universe_id: int, names: list[str]) -> list[str]:
        """Roster confirmation is authoritative, not additive: deletes any
        character row for this universe that isn't in the confirmed list.
        create_universe's own upsert only ever adds rows (INSERT ... ON
        CONFLICT DO NOTHING) — without this, a human removing a fabricated
        name in DCS before approving would see it silently reappear, sourced
        from an earlier placeholder registration (stage 1's own draft push)
        that create_universe never cleans up after."""
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM characters WHERE universe_id = %s AND NOT (name = ANY(%s)) RETURNING name",
                (universe_id, names),
            )
            removed = [row[0] for row in cur.fetchall()]
        return removed

    @logged(lambda _, self, universe_id, name, image_bytes, content_type="image/jpeg":
            f"saved portrait ({len(image_bytes)} byte(s)) for {name!r} (universe {universe_id})")
    @transactional
    def save_character_portrait(self, conn, universe_id: int, name: str,
                                 image_bytes: bytes, content_type: str = "image/jpeg") -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE characters SET image_bytes = %s, image_content_type = %s "
                "WHERE universe_id = %s AND name = %s",
                (psycopg2.Binary(image_bytes), content_type, universe_id, name),
            )

    @logged(lambda _, self, universe_id, name, existence_hits:
            f"saved existence_hits={existence_hits} for {name!r} (universe {universe_id})")
    @transactional
    def save_character_existence_hits(self, conn, universe_id: int, name: str,
                                       existence_hits: int | None) -> None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE characters SET existence_hits = %s WHERE universe_id = %s AND name = %s",
                (existence_hits, universe_id, name),
            )

    @read_only
    def get_character_portrait(self, conn, universe_id: int, name: str) -> tuple[bytes, str] | None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT image_bytes, image_content_type FROM characters WHERE universe_id = %s AND name = %s",
                (universe_id, name),
            )
            row = cur.fetchone()
        if row is None or row[0] is None:
            return None
        return bytes(row[0]), row[1] or "image/jpeg"

    @logged(lambda _, self, universe_id, old_name, new_name:
            f"renamed {old_name!r} -> {new_name!r} in universe {universe_id} (cascaded to groups/relations)")
    @transactional
    def rename_character(self, conn, universe_id: int, old_name: str, new_name: str) -> None:
        """Renames a confirmed character — post-approval, so it's not the
        DCS roster-review edit path (that edits a pending draft before
        anything is in Postgres). `name` is used as the join key in
        `groups.members`/`leader` and `relations.source`/`target`/`members`
        (all plain text/JSONB, not a foreign key), so a rename has to
        cascade into those too or they'd silently point at a name that no
        longer exists. Done in Python, not raw JSONB SQL — clearer to read
        and this is a rare, low-frequency admin action, not a hot path."""
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE characters SET name = %s WHERE universe_id = %s AND name = %s",
                (new_name, universe_id, old_name),
            )
            if cur.rowcount == 0:
                raise ValueError(f"character {old_name!r} not found in universe {universe_id}")

            cur.execute(
                "SELECT id, members, leader FROM groups WHERE universe_id = %s "
                "AND (members @> %s::jsonb OR leader = %s)",
                (universe_id, Json([old_name]), old_name),
            )
            for gid, members, leader in cur.fetchall():
                new_members = [new_name if m == old_name else m for m in (members or [])]
                new_leader = new_name if leader == old_name else leader
                cur.execute(
                    "UPDATE groups SET members = %s, leader = %s WHERE id = %s",
                    (Json(new_members), new_leader, gid),
                )

            cur.execute(
                "SELECT id, source, target, members FROM relations WHERE universe_id = %s "
                "AND (source = %s OR target = %s OR members @> %s::jsonb)",
                (universe_id, old_name, old_name, Json([old_name])),
            )
            for rid, source, target, members in cur.fetchall():
                new_source = new_name if source == old_name else source
                new_target = new_name if target == old_name else target
                new_members = ([new_name if m == old_name else m for m in members]
                               if members is not None else None)
                cur.execute(
                    "UPDATE relations SET source = %s, target = %s, members = %s WHERE id = %s",
                    (new_source, new_target, Json(new_members) if new_members is not None else None, rid),
                )

    @logged(lambda _, self, universe_id, name, fields:
            f"updated profile field(s) {sorted(fields)} for {name!r} (universe {universe_id})" if fields else None)
    @transactional
    def update_character_profile(self, conn, universe_id: int, name: str, fields: dict) -> None:
        """Partial update of aliases + the 4 profile columns — only keys
        present in `fields` change, same "sparse diff is fine" convention
        as save_feature_positions. Ordinal/flag positions have their own
        dedicated writer (save_feature_positions, the Observe Beauty
        path) and aren't touched here."""
        allowed = {"aliases", *_PROFILE_COLUMNS}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown profile field(s): {sorted(unknown)}")
        if not fields:
            return
        assignments = []
        values = []
        for key, value in fields.items():
            assignments.append(f"{key} = %s")
            values.append(Json(value) if key == "aliases" else value)
        values += [universe_id, name]
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE characters SET {', '.join(assignments)} WHERE universe_id = %s AND name = %s",
                values,
            )

    @read_only
    def get_feature_positions(self, conn, universe_id: int, param_name: str) -> dict[str, int | None]:
        """param_name: any ordinal or flag column — one INT per character,
        NULL = unconfirmed. Read side of the "Observe Beauty" ranking view."""
        validate_column(param_name, set(_FEATURE_COLUMNS))
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT name, {param_name} FROM characters WHERE universe_id = %s",
                (universe_id,),
            )
            rows = cur.fetchall()
        return dict(rows)

    @logged(lambda _, self, universe_id, param_name, positions:
            f"saved {param_name} positions for {len(positions)} character(s) (universe {universe_id})")
    @transactional
    def save_feature_positions(self, conn, universe_id: int, param_name: str,
                                positions: dict[str, int | None]) -> None:
        """Overwrites this parameter's position for every named character —
        a manual re-rank/delete in the "Observe Beauty" view confirming into
        Postgres. A name not in `positions` is left untouched (not nulled) —
        callers pass the full edited set, not a sparse diff."""
        validate_column(param_name, set(_FEATURE_COLUMNS))
        with conn.cursor() as cur:
            for name, position in positions.items():
                cur.execute(
                    f"UPDATE characters SET {param_name} = %s WHERE universe_id = %s AND name = %s",
                    (position, universe_id, name),
                )

import logging

from psycopg2.extras import Json

from src.domain.group import Group
from src.infra.exceptions import falseGroupTypeException
from src.repository.connection import read_only, transactional

log = logging.getLogger(__name__)

GROUP_CALL_TYPES: set[str] = {"small", "medium", "large", "isolates"}


def _load_groups(conn, universe_id: int) -> list[Group]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, group_type, members, name_variants, passes "
            "FROM groups WHERE universe_id = %s ORDER BY group_type, name",
            (universe_id,),
        )
        rows = cur.fetchall()
    return [
        Group(name=name, group_type=group_type, members=members,
              name_variants=name_variants, passes=passes)
        for name, group_type, members, name_variants, passes in rows
    ]


class GroupRepository:

    @read_only
    def get_groups(self, conn, universe_id: int) -> list[Group]:
        return _load_groups(conn, universe_id)

    @transactional
    def save_groups(self, conn, groups: list[dict], universe_id: int, group_type: str,
                     replace: bool = False) -> None:
        # Input: the MERGED/consolidated list for one group_type, one entry
        # per surviving cluster (not one per raw pass) — see
        # src/services/collection/cast/groups.py.
        # replace=True: this universe/group_type's existing rows are deleted
        # first — used by the DCS confirm flow, where a re-approval should
        # replace the prior confirmed set, not pile duplicate rows on top of
        # it (a plain re-run without replace= does exactly that today).
        if group_type not in GROUP_CALL_TYPES:
            raise falseGroupTypeException()
        with conn.cursor() as cur:
            if replace:
                cur.execute(
                    "DELETE FROM groups WHERE universe_id = %s AND group_type = %s",
                    (universe_id, group_type),
                )
            for group in groups:
                cur.execute(
                    """INSERT INTO groups (universe_id, name, group_type, members, name_variants, passes)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (universe_id, group["name"], group_type, Json(group["members"]),
                     Json(group["name_variants"]), Json(group["passes"])),
                )
        log.info("saved %d %s groups for universe %d (replace=%s)", len(groups), group_type, universe_id, replace)

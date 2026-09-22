import logging

from psycopg2.extras import Json

from src.domain.relation import GroupRelation, Relation
from src.infra.exceptions import falseRelationTypeException
from src.repository.connection import read_only, transactional

log = logging.getLogger(__name__)

# relation_type -> "directed" (source/target) or "symmetric" (members)
RELATION_TYPES: dict[str, str] = {"for": "directed", "against": "symmetric", "want": "directed", "with": "symmetric"}


class RelationRepository:

    @read_only
    def get_relations(self, conn, universe_id: int) -> list[Relation]:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT relation_type, source, target, members, count, source_level "
                "FROM relations WHERE universe_id = %s",
                (universe_id,),
            )
            rows = cur.fetchall()
        return [
            Relation(relation_type=rt, count=count, source_level=level,
                      members=members, source=source, target=target)
            for rt, source, target, members, count, level in rows
        ]

    @transactional
    def save_relations(self, conn, entries: list[dict], universe_id: int, relation_type: str,
                        replace: bool = False) -> None:
        # Input: the MERGED list for one relation_type — directed entries are
        # {"source", "target", "count", "source_level"}, symmetric entries
        # are {"members", "count", "source_level"}. `count`/`source_level`
        # are never summed across two rows with different source_level (see
        # PIPELINE.md, Этап 3 -> Сведение).
        # replace=True: this universe/relation_type's existing rows are
        # deleted first — used by the DCS confirm flow, see
        # GroupRepository.save_groups's replace= for the same rationale.
        if relation_type not in RELATION_TYPES:
            raise falseRelationTypeException()
        directed = RELATION_TYPES[relation_type] == "directed"
        with conn.cursor() as cur:
            if replace:
                cur.execute(
                    "DELETE FROM relations WHERE universe_id = %s AND relation_type = %s",
                    (universe_id, relation_type),
                )
            for rel in entries:
                if directed:
                    cur.execute(
                        """INSERT INTO relations (universe_id, relation_type, source, target, count, source_level)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (universe_id, relation_type, rel["source"], rel["target"],
                         rel["count"], rel["source_level"]),
                    )
                else:
                    cur.execute(
                        """INSERT INTO relations (universe_id, relation_type, members, count, source_level)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (universe_id, relation_type, Json(rel["members"]),
                         rel["count"], rel["source_level"]),
                    )
        log.info("saved %d %s relations for universe %d (replace=%s)", len(entries), relation_type, universe_id, replace)

    @read_only
    def get_group_relations(self, conn, universe_id: int) -> list[GroupRelation]:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT group_a, group_b, kind FROM group_relations WHERE universe_id = %s",
                (universe_id,),
            )
            rows = cur.fetchall()
        return [GroupRelation(group_a=a, group_b=b, kind=kind) for a, b, kind in rows]

    @transactional
    def save_group_relations(self, conn, group_relations: dict, universe_id: int,
                              replace: bool = False) -> None:
        # Separate table, never merged into character-level `relations`.
        # Input: {"allied": [[group_a, group_b], ...], "rival": [...]}.
        # replace=True: this universe's existing rows are deleted first —
        # same rationale as save_relations/save_groups's replace=, for a
        # re-run against improved group_relations prompts.
        total = 0
        with conn.cursor() as cur:
            if replace:
                cur.execute("DELETE FROM group_relations WHERE universe_id = %s", (universe_id,))
            for kind, pairs in group_relations.items():
                for group_a, group_b in pairs:
                    cur.execute(
                        """INSERT INTO group_relations (universe_id, group_a, group_b, kind)
                           VALUES (%s, %s, %s, %s)""",
                        (universe_id, group_a, group_b, kind),
                    )
                    total += 1
        log.info("saved %d group_relations for universe %d (replace=%s)", total, universe_id, replace)

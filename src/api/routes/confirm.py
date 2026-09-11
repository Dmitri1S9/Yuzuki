"""Where a human's approval in DCS actually lands: these endpoints are the
only place stage 1 (roster+groups) or stage 3 (relations) data gets written
to Postgres for real — the pipeline stages themselves now only push a draft
to DCS, see src/infra/dcs_client.py. replace=True on every write: a
re-approval replaces the previously confirmed set for that universe, it
never piles duplicate rows on top of it.
"""
import logging

from fastapi import APIRouter, HTTPException

from src.api.schemas import RelationsConfirmRequest, RosterConfirmRequest
from src.repository import CharacterRepository, GroupRepository, RelationRepository, UniverseRepository

log = logging.getLogger(__name__)
router = APIRouter(tags=["confirm"])

_universe_repo = UniverseRepository()
_character_repo = CharacterRepository()
_group_repo = GroupRepository()
_relation_repo = RelationRepository()


def _require_universe(universe_id: int):
    if _universe_repo.get_universe_by_id(universe_id) is None:
        raise HTTPException(status_code=404, detail=f"universe {universe_id} not found")


@router.post("/universes/{universe_id}/roster/confirm")
def confirm_roster(universe_id: int, body: RosterConfirmRequest):
    _require_universe(universe_id)

    for character in body.roster:
        if character.aliases:
            _character_repo.save_character_aliases(universe_id, character.name, character.aliases)

    for group_type, groups in body.groups.items():
        _group_repo.save_groups(
            [g.model_dump() for g in groups], universe_id, group_type, replace=True,
        )

    log.info("confirmed roster+groups for universe %d: %d characters, groups=%s",
              universe_id, len(body.roster), {gt: len(gs) for gt, gs in body.groups.items()})
    return {
        "status": "confirmed", "universe_id": universe_id,
        "roster_size": len(body.roster),
        "groups": {gt: len(gs) for gt, gs in body.groups.items()},
    }


@router.post("/universes/{universe_id}/relations/confirm")
def confirm_relations(universe_id: int, body: RelationsConfirmRequest):
    _require_universe(universe_id)

    by_type: dict[str, list[dict]] = {}
    for rel in body.relations:
        entry = {"count": rel.count, "source_level": rel.source_level}
        if rel.members is not None:
            entry["members"] = rel.members
        else:
            entry["source"] = rel.source
            entry["target"] = rel.target
        by_type.setdefault(rel.type, []).append(entry)

    for relation_type, entries in by_type.items():
        _relation_repo.save_relations(entries, universe_id, relation_type, replace=True)

    log.info("confirmed relations for universe %d: %d relations across %d type(s)",
              universe_id, len(body.relations), len(by_type))
    return {
        "status": "confirmed", "universe_id": universe_id,
        "relations_saved": len(body.relations),
    }

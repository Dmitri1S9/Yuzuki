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
    universe = _universe_repo.get_universe_by_id(universe_id)
    if universe is None:
        raise HTTPException(status_code=404, detail=f"universe {universe_id} not found")
    return universe


@router.post("/universes/{universe_id}/roster/confirm")
def confirm_roster(universe_id: int, body: RosterConfirmRequest):
    universe = _require_universe(universe_id)

    # A DCS edit can rename, add, or remove a character — there's no stable
    # id a rename survives (name is the natural key), so a "rename" and a
    # "remove old + add new" look identical here: re-upsert every confirmed
    # name first (create_universe's idempotent INSERT ... ON CONFLICT DO
    # NOTHING) so aliases/isolation/image writes below never silently touch
    # zero rows, then sync_roster deletes anyone no longer in the confirmed
    # list — roster confirmation is authoritative, not additive.
    _universe_repo.create_universe(universe.get_name(), [c.name for c in body.roster], universe.get_arc())
    _character_repo.sync_roster(universe_id, [c.name for c in body.roster])

    for character in body.roster:
        if character.aliases:
            _character_repo.save_character_aliases(universe_id, character.name, character.aliases)
        _character_repo.save_character_isolation(universe_id, character.name, character.is_isolated)
        if character.image_url is not None:
            # Carries image_url/existence_hits through even when this name
            # wasn't in the DB before this confirm — e.g. a DCS rename
            # (Miniskirt Santa -> Nene Iwamizawa, live-confirmed) looks like
            # "delete the old name, add a new one" from sync_roster's plain
            # name-list diff, which would otherwise lose the image stage 1
            # already found for that row.
            _character_repo.save_character_image(
                universe_id, character.name, character.image_url, character.existence_hits)

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

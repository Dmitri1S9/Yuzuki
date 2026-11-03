"""The "Library" view — every character across every universe, browsable by
title or by group/organization, each with local (own-universe) and global
(cross-universe) standing on every ordinal/flag. A read-only aggregation
service over data that already exists elsewhere (characters, groups, the
per-pass CSVs GET /universes/{id}/features/{param} already reads) — not a
new source of truth, so it lives here as a service function over existing
repository reads rather than a change to the Character/Universe domain
classes themselves (see ARCHITECTURE.md's domain-layer convention: those
stay plain read-only data holders).

Also owns manual image upload — the DCS fallback for when stage 1's
automatic web-search portrait (services/collection/cast/images.py) finds
nothing or picks a bad candidate: the human picks and crops their own
image client-side, and this just stores the already-cropped result. No
face detection here — a manually-chosen, manually-cropped image is already
human-verified, unlike a blind web-search result.
"""
import io
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

from src.api.media import portrait_url, portrait_url_for
from src.api.schemas import CharacterEditIn, CharacterProfileOut
from src.domain.parameters import FLAG_PARAMS, ORDINAL_PARAMS
from src.repository import CharacterRepository, GroupRepository, RawPassRepository, UniverseRepository
from src.services.collection.cast.steps import anime_db
from src.services.consensus.flag_consensus import FLAG_PASSES, flag_consensus
from src.services.consensus.ordinal_consensus import PASSES as ORDINAL_PASSES, ordinal_consensus

log = logging.getLogger(__name__)
router = APIRouter(tags=["library"])

_universe_repo = UniverseRepository()
_character_repo = CharacterRepository()
_group_repo = GroupRepository()
_raw_pass_repo = RawPassRepository()


@router.get("/characters")
def list_characters():
    """Every character across every universe — the Library's "by title"
    view is this list grouped client-side by universe_name; "by
    organization" groups it by the groups list from /groups instead."""
    out = []
    for u in _universe_repo.list_universes():
        full = _universe_repo.get_universe_by_id(u.get_id())
        for c in full.get_roster():
            out.append({
                "universe_id": full.get_id(),
                "universe_name": full.get_name(),
                "arc": full.get_arc(),
                "name": c.get_name(),
                "image_url": portrait_url(c),
            })
    return out


@router.get("/groups")
def list_groups():
    """Every group across every universe, for the Library's "by
    organization" view."""
    out = []
    for u in _universe_repo.list_universes():
        for g in _group_repo.get_groups(u.get_id()):
            out.append({
                "universe_id": u.get_id(),
                "universe_name": u.get_name(),
                "arc": u.get_arc(),
                "name": g.get_name(),
                "type": g.get_type(),
                "members": g.get_members(),
            })
    return out


@router.get("/characters/{universe_id}/{name}/description")
def character_description(universe_id: int, name: str):
    """Display-only bio text for the Library detail card — AniList's own
    write-up for this character, fetched live (not persisted, not fed to
    any model prompt — see anime_db.py's module docstring)."""
    universe = _universe_repo.get_universe_by_id(universe_id)
    if universe is None:
        raise HTTPException(status_code=404, detail=f"universe {universe_id} not found")
    descriptions = anime_db.fetch_character_descriptions(universe.get_anilist_title())
    return {"description": anime_db.lookup(name, descriptions)}


@router.patch("/characters/{universe_id}/{name}", response_model=CharacterProfileOut)
def edit_character(universe_id: int, name: str, body: CharacterEditIn):
    """General character edit for a CONFIRMED character — the Library
    "edit" affordance, distinct from RosterReview's pending-draft edit
    (that one edits the DCS queue payload before anything is in Postgres
    at all). Only fields actually present in the request change."""
    character = _character_repo.get_character_or_raise(universe_id, name)

    fields = body.model_dump(exclude_unset=True, exclude={"new_name"})
    current_name = name
    if body.new_name and body.new_name != name:
        try:
            _character_repo.rename_character(universe_id, name, body.new_name)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        current_name = body.new_name

    if fields:
        _character_repo.update_character_profile(universe_id, current_name, fields)

    character = _character_repo.get_character(universe_id, current_name)
    return CharacterProfileOut(
        name=character.get_name(),
        aliases=character.get_aliases(),
        image_url=portrait_url(character),
        existence_hits=character.get_existence_hits(),
        body_age=character.get_profile_field("body_age"),
        soul_age=character.get_profile_field("soul_age"),
        gender=character.get_profile_field("gender"),
        species=character.get_profile_field("species"),
    )


def _param_standing(param_name: str, target_universe_id: int, target_name: str, is_ordinal: bool) -> dict:
    """local: this character's own tier/sub_position within its own
    universe. local_rank/local_total: where this character's consensus_z
    ranks among every OTHER character in the SAME universe with a real
    placement for this param (1 = highest z) — plain "X of Y" within the
    cast, not a cross-universe pool. Cross-universe percentile pooling
    (every universe's own distribution, different sample sizes, different
    collection runs) used to feed this and read as noise dressed up as
    precision — "97.9%ile (of 98)" answers a question nobody asked
    (2026-09-23, user's call: drop it, local rank only, for now).

    Reads the DB-backed raw-pass cache (RawPassRepository), same source
    GET .../features/{param} uses — not the old per-universe pass{N}.csv
    files, which no stage has written since the raw_passes migration.
    Ordinals and flags are collected at different pass counts (ORDINAL_
    PASSES=(1,2) vs FLAG_PASSES=(1,)) and reconciled through different
    consensus functions — same split as features.py's get_feature."""
    passes = ORDINAL_PASSES if is_ordinal else FLAG_PASSES
    consensus_fn = ordinal_consensus if is_ordinal else flag_consensus
    all_passes = _raw_pass_repo.get_passes(target_universe_id, passes, {param_name})
    if all_passes is None:
        return {"local": None, "local_rank": None, "local_total": 0}

    per_pass_scores = {p: all_passes[p].get(param_name, {}) for p in passes}
    roster = sorted({n for p in passes for n in per_pass_scores[p]})
    per_character, _ = consensus_fn(per_pass_scores, roster)
    local = per_character.get(target_name)

    placed = [(name, cell["consensus_z"]) for name, cell in per_character.items()
              if cell and cell.get("consensus_z") is not None]
    if not placed:
        return {"local": local, "local_rank": None, "local_total": 0}

    placed.sort(key=lambda t: t[1], reverse=True)  # rank 1 = highest z
    total = len(placed)
    rank = next((i for i, t in enumerate(placed) if t[0] == target_name), None)
    return {
        "local": local,
        "local_rank": (rank + 1) if rank is not None else None,
        "local_total": total,
    }


@router.get("/characters/{universe_id}/{name}/standing")
def character_standing(universe_id: int, name: str):
    _character_repo.get_character_or_raise(universe_id, name)

    return {
        **{param: _param_standing(param, universe_id, name, True) for param in ORDINAL_PARAMS},
        **{param: _param_standing(param, universe_id, name, False) for param in FLAG_PARAMS},
    }


@router.post("/universes/{universe_id}/characters/{name}/upload-image", response_model=CharacterProfileOut)
async def upload_character_image(universe_id: int, name: str, file: UploadFile = File(...)):
    character = _character_repo.get_character_or_raise(universe_id, name)

    raw = await file.read()
    try:
        image = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="not a readable image")

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=90)
    _character_repo.save_character_portrait(universe_id, name, buf.getvalue())

    return CharacterProfileOut(
        name=name,
        aliases=character.get_aliases(),
        image_url=portrait_url_for(universe_id, name),
        existence_hits=character.get_existence_hits(),
        body_age=character.get_profile_field("body_age"),
        soul_age=character.get_profile_field("soul_age"),
        gender=character.get_profile_field("gender"),
        species=character.get_profile_field("species"),
    )

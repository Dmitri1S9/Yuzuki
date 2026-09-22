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
import csv
import hashlib
import io
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

from src.api.schemas import CharacterEditIn, CharacterProfileOut
from src.domain.parameters import FLAG_PARAMS, ORDINAL_PARAMS
from src.repository import CharacterRepository, GroupRepository, UniverseRepository
from src.services.collection.cast.steps import anime_db
from src.services.collection.cast.steps.images import MEDIA_DIR, YUZUKI_PUBLIC_URL
from src.services.consensus.flag_consensus import FLAG_PASSES, flag_consensus
from src.shared.naming import slugify

log = logging.getLogger(__name__)
router = APIRouter(tags=["library"])

_universe_repo = UniverseRepository()
_character_repo = CharacterRepository()
_group_repo = GroupRepository()

RUN_DIR = "run"


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
                "image_url": c.get_image_url(),
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
    character = _character_repo.get_character(universe_id, name)
    if character is None:
        raise HTTPException(status_code=404, detail=f"character {name!r} not found in universe {universe_id}")

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
        image_url=character.get_image_url(),
        existence_hits=character.get_existence_hits(),
        body_age=character.get_profile_field("body_age"),
        soul_age=character.get_profile_field("soul_age"),
        gender=character.get_profile_field("gender"),
        species=character.get_profile_field("species"),
    )


def _read_pass_csv(slug: str, pass_number: int, param_name: str) -> dict[str, float | None] | None:
    path = os.path.join(RUN_DIR, f"pass{pass_number}_{slug}.csv")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows or param_name not in rows[0]:
        return None
    return {row["entity"]: (None if row.get(param_name) in (None, "", "None") else float(row[param_name]))
            for row in rows}


def _param_standing(param_name: str, target_universe_id: int, target_name: str) -> dict:
    """local: this character's own tier/sub_position within its own
    universe. global_percentile: where consensus_z for this character
    ranks among every character (from every universe that has collected
    this parameter) — consensus_z is a standardized (mean-0) position
    within its own universe's distribution already, so pooling it across
    universes is the same trick GET .../features/{param} uses for a single
    universe, just applied over all of them at once."""
    pooled: list[tuple[str, int, float]] = []
    local = None
    for u in _universe_repo.list_universes():
        slug = slugify(u.get_name(), u.get_arc())
        per_pass_scores = {p: (_read_pass_csv(slug, p, param_name) or {}) for p in FLAG_PASSES}
        if not any(per_pass_scores[p] for p in FLAG_PASSES):
            continue
        roster = sorted({n for p in FLAG_PASSES for n in per_pass_scores[p]})
        per_character, _ = flag_consensus(per_pass_scores, roster)
        for name, cell in per_character.items():
            if not cell or cell.get("consensus_z") is None:
                continue
            pooled.append((name, u.get_id(), cell["consensus_z"]))
            if u.get_id() == target_universe_id and name == target_name:
                local = cell

    if not pooled:
        return {"local": local, "global_percentile": None, "global_rank": None, "global_total": 0}

    pooled.sort(key=lambda t: t[2])
    total = len(pooled)
    rank = next((i for i, t in enumerate(pooled) if t[1] == target_universe_id and t[0] == target_name), None)
    percentile = round(100 * rank / (total - 1), 1) if rank is not None and total > 1 else None
    return {
        "local": local,
        "global_percentile": percentile,
        "global_rank": (rank + 1) if rank is not None else None,
        "global_total": total,
    }


@router.get("/characters/{universe_id}/{name}/standing")
def character_standing(universe_id: int, name: str):
    character = _character_repo.get_character(universe_id, name)
    if character is None:
        raise HTTPException(status_code=404, detail=f"character {name!r} not found in universe {universe_id}")

    return {
        param: _param_standing(param, universe_id, name)
        for param in list(ORDINAL_PARAMS) + list(FLAG_PARAMS)
    }


@router.post("/universes/{universe_id}/characters/{name}/upload-image", response_model=CharacterProfileOut)
async def upload_character_image(universe_id: int, name: str, file: UploadFile = File(...)):
    universe = _universe_repo.get_universe_by_id(universe_id)
    if universe is None:
        raise HTTPException(status_code=404, detail=f"universe {universe_id} not found")
    character = _character_repo.get_character(universe_id, name)
    if character is None:
        raise HTTPException(status_code=404, detail=f"character {name!r} not found in universe {universe_id}")

    raw = await file.read()
    try:
        image = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="not a readable image")

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    slug = hashlib.sha1(f"{universe.get_name()}|{name}".encode()).hexdigest()[:16]
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=90)
    (MEDIA_DIR / f"{slug}.jpg").write_bytes(buf.getvalue())
    image_url = f"{YUZUKI_PUBLIC_URL}/media/characters/{slug}.jpg?v={int(time.time())}"

    _character_repo.save_character_image(universe_id, name, image_url, character.get_existence_hits())

    return CharacterProfileOut(
        name=name,
        aliases=character.get_aliases(),
        image_url=image_url,
        existence_hits=character.get_existence_hits(),
        body_age=character.get_profile_field("body_age"),
        soul_age=character.get_profile_field("soul_age"),
        gender=character.get_profile_field("gender"),
        species=character.get_profile_field("species"),
    )

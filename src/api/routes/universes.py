"""Read-only universe browsing — thin wrappers over UniverseRepository."""
from ddgs import DDGS
from fastapi import APIRouter, HTTPException

from src.api.media import portrait_url
from src.api.schemas import CharacterProfileOut, UniverseOut
from src.repository import CharacterRepository, UniverseRepository
from src.services.collection.cast.steps import anime_db
from src.services.collection.cast.steps.images import lookup_character_image

router = APIRouter(tags=["universes"])
_universe_repo = UniverseRepository()
_character_repo = CharacterRepository()


@router.get("/universes", response_model=list[UniverseOut])
def list_universes():
    universes = _universe_repo.list_universes()
    return [UniverseOut(id=u.get_id(), name=u.get_name(), arc=u.get_arc()) for u in universes]


@router.get("/universes/{universe_id}", response_model=UniverseOut)
def get_universe(universe_id: int):
    u = _universe_repo.get_universe_by_id(universe_id)
    if u is None:
        raise HTTPException(status_code=404, detail=f"universe {universe_id} not found")
    return UniverseOut(id=u.get_id(), name=u.get_name(), arc=u.get_arc())


@router.get("/universes/{universe_id}/characters/{name}/profile", response_model=CharacterProfileOut)
def get_character_profile(universe_id: int, name: str):
    character = _character_repo.get_character_or_raise(universe_id, name)
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


@router.post("/universes/{universe_id}/characters/{name}/refresh-image", response_model=CharacterProfileOut)
def refresh_character_image(universe_id: int, name: str):
    """Re-runs stage 1's face-verified image search for one character, on
    demand — the "click to update the picture" button in DCS."""
    universe = _universe_repo.get_universe_by_id(universe_id)
    if universe is None:
        raise HTTPException(status_code=404, detail=f"universe {universe_id} not found")
    _character_repo.get_character_or_raise(universe_id, name)

    # AniList images come from the universe's own anilist_title (falls
    # back to its display name if none was set) — see Universe.get_anilist_title().
    anilist_images = anime_db.fetch_character_images(universe.get_anilist_title())
    with DDGS() as ddgs:
        image_bytes, existence_hits = lookup_character_image(ddgs, name, universe.get_name(), anilist_images)
    if image_bytes:
        _character_repo.save_character_portrait(universe_id, name, image_bytes)
    _character_repo.save_character_existence_hits(universe_id, name, existence_hits)
    character = _character_repo.get_character_or_raise(universe_id, name)  # has_portrait may have just changed

    return CharacterProfileOut(
        name=name,
        aliases=character.get_aliases(),
        image_url=portrait_url(character),
        existence_hits=existence_hits,
        body_age=character.get_profile_field("body_age"),
        soul_age=character.get_profile_field("soul_age"),
        gender=character.get_profile_field("gender"),
        species=character.get_profile_field("species"),
    )

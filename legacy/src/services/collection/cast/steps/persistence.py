"""Registers the universe/roster in Postgres, then hands the roster+groups
draft to DCS for human review — DCS calls back into
src/api/routes/confirm.py once approved, which is the only place aliases
and groups actually get written. See ARCHITECTURE.md's DCS section.
"""
from src.infra.dcs_client import push_roster_draft
from src.repository import UniverseRepository
from src.services.collection.cast.steps.constants import ANILIST_TITLE, ARC, UNIVERSE_NAME
from src.shared.decorators import announce, logged
from src.shared.media_url import portrait_url_for

_universe_repo = UniverseRepository()


@logged(lambda universe_id, output: f"universe_id={universe_id}, roster registered ({len(output['roster'])} characters)")
@announce("registering universe + roster in database")
def persist_to_database(output: dict) -> int:
    # Idempotent (upserts on name+arc) — just enough scaffolding to have a
    # real universe_id to tag the DCS draft with. Aliases and groups are
    # NOT written here; they only land once DCS confirms the review.
    # anilist_title is only saved when it actually differs from the
    # display name, so a per-character refresh/description lookup later
    # (universes.py, library.py) keeps using the same title this run did.
    saved_anilist_title = ANILIST_TITLE if ANILIST_TITLE != UNIVERSE_NAME else None
    universe_id = _universe_repo.create_universe(
        UNIVERSE_NAME, [r["name"] for r in output["roster"]], ARC, saved_anilist_title)
    return universe_id


@announce("pushing roster + groups draft to DCS for review")
def push_draft_to_dcs(output: dict, universe_id: int) -> None:
    # DCS only ever sees a URL (RosterCharacterIn.image_url), never bytes —
    # images.py's collect_character_images left raw image_bytes on these
    # dicts for persist_character_images to write to Postgres; that key
    # can't cross this boundary (not JSON-serializable, and not DCS's
    # concern), so it's swapped for the portrait's URL here, right before
    # the draft leaves the process.
    roster = [
        {**{k: v for k, v in r.items() if k != "image_bytes"},
         "image_url": portrait_url_for(universe_id, r["name"]) if r.get("image_bytes") else None}
        for r in output["roster"]
    ]
    push_roster_draft(universe_id, UNIVERSE_NAME, ARC, roster, output["groups"])

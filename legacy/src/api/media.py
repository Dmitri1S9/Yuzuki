"""Portrait URL building for API responses — src/shared/media_url.py has
the actual URL shape (shared with the DCS draft push in
services/collection/cast), this just adds the Character-aware convenience."""
from src.domain.character import Character
from src.shared.media_url import portrait_url_for


def portrait_url(character: Character) -> str | None:
    if not character.has_portrait():
        return None
    return portrait_url_for(character.get_universe_id(), character.get_name())

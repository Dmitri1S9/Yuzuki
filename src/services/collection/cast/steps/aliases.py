"""Alias resolution — was a dedicated LLM call (see git history), now free:
AniList's own cast list already carries each character's native/codename
spelling (name.native, name.alternative), fetched once alongside the
roster backstop (anime_db.fetch_cast_aliases). This only attaches alias
text to an EXISTING canon entry, matched by the character's own full name
through the spelling resolver — unlike the old LLM call, it cannot merge
two canon entries that turn out to be the same character under an
unrelated name (e.g. a codename with no shared spelling), since that needs
real-world knowledge no amount of string matching recovers. A human still
catches that case in DCS's roster review (rename/merge is already manual
there).
"""
import logging

from src.shared.decorators import announce, report

log = logging.getLogger(__name__)


@announce("attaching AniList alias data to the roster (free, no model call)")
@report(lambda r: f"aliases_attached={len(r)}")
def merge_anilist_aliases(canon: dict, resolve, anilist_aliases: dict[str, list[str]]) -> dict:
    # resolve: build_name_resolver's closure — takes a raw name string and
    # runs name_key() + the spelling map internally, so a raw AniList full
    # name goes in directly, not a pre-computed key.
    aliases_of: dict[str, list[str]] = {}
    for full_name, alts in anilist_aliases.items():
        key = resolve(full_name)
        if key not in canon:
            continue
        real_alts = [a for a in alts if a != canon[key]]
        if real_alts:
            aliases_of[key] = real_alts
    return aliases_of

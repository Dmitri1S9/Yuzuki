"""Request/response shapes for the confirm endpoints DCS calls. The queue
payloads DCS stores itself are its own concern (see DCS/backend) — these
schemas only describe what crosses back into Yuzuki once a human has
approved something.
"""
from pydantic import BaseModel


class GroupIn(BaseModel):
    name: str
    members: list[str]
    name_variants: list[str] = []
    passes: list[int] = []


class RosterCharacterIn(BaseModel):
    name: str
    aliases: list[str] = []
    is_isolated: bool = False
    image_url: str | None = None
    existence_hits: int | None = None


class PipelineRunRequest(BaseModel):
    universe_id: int


class RosterConfirmRequest(BaseModel):
    roster: list[RosterCharacterIn]
    groups: dict[str, list[GroupIn]]  # {"medium": [...], "large": [...]}


class RelationIn(BaseModel):
    type: str  # for | against | want | with
    count: int
    source_level: str
    members: list[str] | None = None  # symmetric (against/with)
    source: str | None = None          # directed (for/want)
    target: str | None = None


class RelationsConfirmRequest(BaseModel):
    relations: list[RelationIn]


class UniverseOut(BaseModel):
    id: int
    name: str
    arc: str | None


class CharacterProfileOut(BaseModel):
    name: str
    aliases: list[str]
    image_url: str | None
    existence_hits: int | None
    body_age: str | None
    soul_age: str | None
    gender: str | None
    species: str | None


class CharacterEditIn(BaseModel):
    # Every field optional — only the ones actually sent are changed. A
    # rename (new_name set and different from the current name) cascades
    # into groups.members/leader and relations.source/target/members, see
    # CharacterRepository.rename_character.
    new_name: str | None = None
    aliases: list[str] | None = None
    body_age: str | None = None
    soul_age: str | None = None
    gender: str | None = None
    species: str | None = None


class FeatureCharacterOut(BaseModel):
    name: str
    block_index: int | None    # tied characters share a block_index — same tier
    consensus_z: float | None  # standardized position, None = not placed by consensus
    tier: int | None = None    # this response's raw tier (0-indexed) — for ordinals,
                                # a position on the fixed T1..Tn scale; for flags, just
                                # this response's own tier numbering
    sub_position: float | None = None  # tier + fractional rank within the tie
                                        # block (e.g. 3 people in tier 3 ->
                                        # 3.25/3.50/3.75), for display/cross-
                                        # universe ordering only — never
                                        # changes which block someone is in


class FeatureScaleOut(BaseModel):
    # Ordinals only — the fixed tier scale characters sit on, and where its
    # "ordinary person" anchor tier is (see parameters.json's
    # normal_tier_index). None for flags: they have no fixed tier count, a
    # response can mark as many tiers as the model chose to.
    tier_count: int
    normal_tier_index: int


class FeatureDetailOut(BaseModel):
    param_name: str
    is_ordinal: bool
    definition: str                         # what this parameter means
    tier_labels: list[str] = []             # ordinals only: T1..Tn calibration text, index 0 = T1
    characters: list[FeatureCharacterOut]   # fresh consensus result, recomputed on every request
    positions: dict[str, int | None]        # last confirmed position, from Postgres
    scale: FeatureScaleOut | None = None    # present only when is_ordinal


class FeatureConfirmRequest(BaseModel):
    positions: dict[str, int | None]

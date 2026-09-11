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

"""JSON schemas for the two LLM passes."""
from typing import Literal

from pydantic import BaseModel


class RewriteReply(BaseModel):
    simple_sentences: list[str]


class ParseReply(BaseModel):
    kind: Literal["edge", "property"]
    subject: str
    subject_type: Literal["character", "group", "people"]
    predicate: str
    predicate_raw: str
    property: str
    target: str
    target_type: Literal["character", "group", "people", "concept"]
    via: str
    description: str
    modality: Literal["none", "want", "can", "must"]
    negated: bool
    mutual: bool
    frequency: str
    degree: str
    certainty: Literal["fact", "implied", "rumored"]
    former: bool

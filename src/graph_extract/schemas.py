"""JSON schema of the chunk-extraction LLM answer: ACTION edges + DESCRIBED_AS (trait) edges."""
from typing import Literal

from pydantic import BaseModel


class ActionEdgeReply(BaseModel):
    subject: str
    subject_type: Literal["character", "group", "people"]
    action: str
    action_raw: str
    manner: str
    target: str
    target_type: Literal["character", "group", "people", "concept"]
    complement: str
    modality: Literal["did", "wants", "can", "must"]
    negated: bool
    source_sentence: str


class DescribedAsReply(BaseModel):
    character: str
    trait: str
    said_by: str
    negated: bool
    source_sentence: str


class ChunkExtractionReply(BaseModel):
    actions: list[ActionEdgeReply]
    traits: list[DescribedAsReply]

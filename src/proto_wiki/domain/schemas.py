"""Pydantic models for everything the prototype sends to or reads from the
LLM, plus the on-disk shapes. Model.model_json_schema() goes straight into
Ollama's `format`, so every closed vocabulary here is a Literal (-> `enum`
in the schema) and not just a sentence in a prompt.
"""
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, create_model

# target node type -> relations a Character can have towards it. Every
# relation has a Character subject; the group fixes what the object may be.
RELATIONS_BY_OBJECT_TYPE: dict[str, tuple[str, ...]] = {
    "Character": (
        "family_of", "friend_of", "rival_of", "enemy_of", "mentor_of", "student_of", "ally_of",
        "subordinate_of", "romantic_interest", "protects", "admires", "hates", "fears",
    ),
    "Organization": ("member_of", "leader_of", "opposes"),
    "Item": ("owns", "uses", "created"),
    "Concept": ("believes_in", "pursues", "rejects"),
    "Activity": ("enjoys", "skilled_in"),
}
RELATION_OBJECT_TYPE: dict[str, str] = {
    rel: obj_type for obj_type, rels in RELATIONS_BY_OBJECT_TYPE.items() for rel in rels
}
RELATIONS = tuple(RELATION_OBJECT_TYPE)
NODE_TYPES = ("Character", "Organization", "Item", "Concept", "Activity")
ITEM_CLASSES = ("weapon", "artifact", "tool", "equipment", "vehicle", "other", "none")

RelationName = Literal[RELATIONS]
NodeType = Literal[NODE_TYPES]
ItemClass = Literal[ITEM_CLASSES]


# --- step 1 ---------------------------------------------------------------

class CorefOutput(BaseModel):
    text: str


class ResolvedParagraph(BaseModel):
    section: str
    original: str
    resolved: str
    coref_ok: bool
    error: str | None = None


# --- step 2 ---------------------------------------------------------------

class TripleLLM(BaseModel):
    sentence_id: int
    subject: str
    subject_type: NodeType
    relation: RelationName
    object: str
    object_type: NodeType
    item_class: ItemClass


class TriplesOutput(BaseModel):
    triples: list[TripleLLM]


class Triple(TripleLLM):
    evidence: str
    section: str


# --- step 3 ---------------------------------------------------------------

class ParamResult(BaseModel):
    name: str
    ordinal: bool
    tier: str | None  # None only when status == "error"; a failure is never "unknown"
    evidence: str
    reason: str
    status: Literal["ok", "evidence_not_found", "error"]


@lru_cache(maxsize=None)
def answer_model(tiers: tuple[str, ...]) -> type[BaseModel]:
    # Field order is generation order under structured output: quote first,
    # then reasoning, then the verdict — the verdict has to follow from the
    # quote, not the other way round.
    return create_model(
        "ParamAnswer",
        evidence=(str, ...),
        reason=(str, ...),
        tier=(Literal[tiers], ...),
    )


# --- graph ----------------------------------------------------------------

class GraphNode(BaseModel):
    id: str
    type: str


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str
    count: int


class Graph(BaseModel):
    center: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]

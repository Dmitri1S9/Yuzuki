"""Слой графовой БД (Neo4j) — ЗАГЛУШКА. Реализацию владелец пишет сам.

Здесь только форма данных, которую производят эксперименты research/exp (и будущий пайплайн),
чтобы слой БД и извлечение договорились об интерфейсе. Предложение по модели графа — ARCHITECTURE.md.
"""
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class EntityRecord:
    universe: str
    name: str                              # каноническое имя = заголовок страницы вики
    kind: Literal["character", "group"]
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationRecord:
    universe: str
    source: str                            # владелец страницы, с которой извлечено
    target: str
    type: str                              # research/exp/taxonomy.py: REL_TYPE_ENUM
    affinity: Literal["positive", "neutral", "negative"]
    evidence: str                          # дословная цитата
    paragraph_id: str                      # "page|section|idx"
    method: str                            # кто извлёк (rel_anchored@qwen3.5:9b, infobox, ...)


@dataclass(frozen=True)
class TraitRecord:
    universe: str
    character: str
    span: str                              # дословный фрагмент
    pole: str                              # research/exp/taxonomy.py: TRAIT_POLES
    paragraph_id: str
    method: str


@dataclass(frozen=True)
class MembershipRecord:
    universe: str
    character: str
    group: str                             # только факт членства, без приоров на черты


class GraphStore(Protocol):
    def upsert_entity(self, e: EntityRecord) -> None: ...
    def add_relation(self, r: RelationRecord) -> None: ...
    def add_trait(self, t: TraitRecord) -> None: ...
    def add_membership(self, m: MembershipRecord) -> None: ...


class Neo4jGraphStore:
    """TODO(владелец): реализация на neo4j-driver. Подсказки — ARCHITECTURE.md §Граф."""

    def __init__(self, uri: str, user: str, password: str):
        raise NotImplementedError("Neo4j layer is written by hand — see ARCHITECTURE.md")

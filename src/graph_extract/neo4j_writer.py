"""Batch UNWIND + MERGE writer, called once per chunk (so a crash mid-run leaves Neo4j holding everything
processed so far, not just what got batched at the very end). Groups action edges by (subject_type,
target_type) so each Cypher statement can use static node labels (no APOC, vanilla Neo4j Community)."""
import hashlib
from datetime import datetime, timezone

from yuzuki_local.external.embedder import Embedder
from yuzuki_local.external.neo4j_client import Neo4jClient

from .extractor import ActionFact, TraitFact
from .resolve import build_lookup, canonicalize
from .settings import RosterEntry

_LABEL = {"character": "Character", "group": "Group", "people": "People", "concept": "Concept"}


def _node_key(kind: str, universe: str, name: str) -> dict:
    if kind == "people":
        return {"universe": universe}
    if kind == "concept":
        return {"name": name}
    return {"id": f"{universe}::{name}"}


def write_roster(client: Neo4jClient, universe: str, characters: tuple[RosterEntry, ...],
                 groups: tuple[RosterEntry, ...]) -> None:
    """Every known roster member gets a node up front, even ones no edge ends up naming."""
    with client.session() as session:
        session.run("MERGE (:Universe {name:$universe})", universe=universe)
        session.run(
            "UNWIND $rows AS row MERGE (n:Character {id: $universe + '::' + row.name}) "
            "SET n.name=row.name, n.aliases=row.aliases, n.universe=$universe",
            universe=universe, rows=[{"name": c.name, "aliases": list(c.aliases)} for c in characters])
        session.run(
            "UNWIND $rows AS row MERGE (n:Group {id: $universe + '::' + row.name}) "
            "SET n.name=row.name, n.aliases=row.aliases, n.universe=$universe",
            universe=universe, rows=[{"name": g.name, "aliases": list(g.aliases)} for g in groups])
        session.run("MERGE (:People {universe:$universe})", universe=universe)


class ChunkWriter:
    """Holds the pieces that don't change per chunk (embedder, roster lookup, run metadata)."""

    def __init__(self, client: Neo4jClient, embedder: Embedder, universe: str, run_id: str, model: str,
                prompt_version: str, characters: tuple[RosterEntry, ...], groups: tuple[RosterEntry, ...]):
        self._client = client
        self._embedder = embedder
        self._universe = universe
        self._run_id = run_id
        self._model = model
        self._prompt_version = prompt_version
        self._lookup = build_lookup(characters, groups)

    def write(self, actions: list[ActionFact], traits: list[TraitFact]) -> tuple[int, int]:
        valid_actions = [a for a in actions if a.valid_source]
        valid_traits = [t for t in traits if t.valid_source]
        created_at = datetime.now(timezone.utc).isoformat()

        action_words = sorted({a.action for a in valid_actions})
        manner_words = sorted({a.manner for a in valid_actions if a.manner})
        concept_names = sorted({a.target for a in valid_actions if a.target_type == "concept"})
        trait_names = sorted({t.trait for t in valid_traits})
        action_vec = self._embed_map(action_words)
        manner_vec = self._embed_map(manner_words)
        concept_vec = self._embed_map(concept_names)
        trait_vec = self._embed_map(trait_names)

        n_actions = self._write_actions(valid_actions, action_vec, manner_vec, concept_vec, created_at)
        n_traits = self._write_traits(valid_traits, trait_vec, created_at)
        return n_actions, n_traits

    def _embed_map(self, words: list[str]) -> dict[str, list[float]]:
        if not words:
            return {}
        vecs = self._embedder.embed(words, is_query=False)
        return {w: [float(x) for x in v] for w, v in zip(words, vecs)}

    def _write_actions(self, actions: list[ActionFact], action_vec, manner_vec, concept_vec, created_at) -> int:
        buckets: dict[tuple[str, str], list[dict]] = {}
        for a in actions:
            subj, _ = canonicalize(a.subject, self._lookup) if a.subject_type in ("character", "group") \
                else (a.subject, False)
            tgt, _ = canonicalize(a.target, self._lookup) if a.target_type in ("character", "group") \
                else (a.target, False)
            key_src = f"{subj}|{a.action}|{tgt}|{a.source_sentence}|{self._run_id}"
            row = dict(
                subj_key=_node_key(a.subject_type, self._universe, subj),
                tgt_key=_node_key(a.target_type, self._universe, tgt),
                action=a.action, action_raw=a.action_raw, action_embedding=action_vec.get(a.action, []),
                manner=a.manner, manner_embedding=manner_vec.get(a.manner, []) if a.manner else [],
                complement=a.complement, modality=a.modality, negated=a.negated,
                source_sentence=a.source_sentence, section=a.section, valid_source=a.valid_source,
                run_id=self._run_id, model=self._model, prompt_version=self._prompt_version,
                created_at=created_at, edge_key=hashlib.sha1(key_src.encode("utf-8")).hexdigest())
            if a.target_type == "concept":
                row["concept_embedding"] = concept_vec.get(tgt, [])
            buckets.setdefault((a.subject_type, a.target_type), []).append(row)

        total = 0
        with self._client.session() as session:
            for (st, tt), rows in buckets.items():
                sl, tl = _LABEL[st], _LABEL[tt]
                set_concept = "SET o.embedding = row.concept_embedding " if tt == "concept" else ""
                cypher = (
                    f"UNWIND $rows AS row "
                    f"MERGE (s:{sl} {{{', '.join(f'{k}: row.subj_key.{k}' for k in rows[0]['subj_key'])}}}) "
                    f"MERGE (o:{tl} {{{', '.join(f'{k}: row.tgt_key.{k}' for k in rows[0]['tgt_key'])}}}) "
                    f"{set_concept}"
                    f"MERGE (s)-[r:ACTION {{edge_key: row.edge_key}}]->(o) "
                    f"SET r.action=row.action, r.action_raw=row.action_raw, r.action_embedding=row.action_embedding, "
                    f"r.manner=row.manner, r.manner_embedding=row.manner_embedding, r.complement=row.complement, "
                    f"r.modality=row.modality, r.negated=row.negated, r.source_sentence=row.source_sentence, "
                    f"r.section=row.section, r.valid_source=row.valid_source, r.run_id=row.run_id, "
                    f"r.model=row.model, r.prompt_version=row.prompt_version, r.created_at=row.created_at"
                )
                session.run(cypher, rows=rows)
                total += len(rows)
        return total

    def _write_traits(self, traits: list[TraitFact], trait_vec, created_at) -> int:
        if not traits:
            return 0
        rows = []
        for t in traits:
            char, _ = canonicalize(t.character, self._lookup)
            said_by, _ = canonicalize(t.said_by, self._lookup) if t.said_by.casefold() != "narrator" else ("narrator", True)
            key_src = f"{char}|{t.trait}|{t.source_sentence}|{self._run_id}"
            rows.append(dict(
                char_id=f"{self._universe}::{char}", trait=t.trait, trait_embedding=trait_vec.get(t.trait, []),
                said_by=said_by, negated=t.negated, source_sentence=t.source_sentence, section=t.section,
                valid_source=t.valid_source, run_id=self._run_id, model=self._model,
                prompt_version=self._prompt_version, created_at=created_at,
                edge_key=hashlib.sha1(key_src.encode("utf-8")).hexdigest()))
        cypher = (
            "UNWIND $rows AS row "
            "MERGE (c:Character {id: row.char_id}) "
            "MERGE (t:Trait {name: row.trait}) SET t.embedding = row.trait_embedding "
            "MERGE (c)-[r:DESCRIBED_AS {edge_key: row.edge_key}]->(t) "
            "SET r.said_by=row.said_by, r.negated=row.negated, r.source_sentence=row.source_sentence, "
            "r.section=row.section, r.valid_source=row.valid_source, r.run_id=row.run_id, r.model=row.model, "
            "r.prompt_version=row.prompt_version, r.created_at=row.created_at"
        )
        with self._client.session() as session:
            session.run(cypher, rows=rows)
        return len(rows)

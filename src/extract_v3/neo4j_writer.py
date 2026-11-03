"""Batch UNWIND + MERGE writer, called once per simple sentence's fact.

Node identity does NOT bake the universe into a composite id string (no "Universe::Name" -- flagged as
wrong mid-session: a node's universe is a fact represented by a real graph edge, not string concatenation).
Character/Group are keyed on `name` alone (single-universe prototype so far) and each gets an explicit
(:Character)-[:IN_UNIVERSE]->(:Universe) edge; that edge is the only place "this belongs to My Hero
Academia" is recorded. People keeps its own `universe` property (that property IS the whole of what a
People node is, by the original schema -- not an id-composite pattern, so it's unaffected by this). Concept
was already plain `name`, unaffected."""
import hashlib
from datetime import datetime, timezone

from .external.embedder import Embedder
from .external.neo4j_client import Neo4jClient

from .resolve import build_lookup
from .schemas import ParseReply
from .settings import RosterEntry

_LABEL = {"character": "Character", "group": "Group", "people": "People", "concept": "Concept"}


def _node_key(kind: str, universe: str, name: str) -> dict:
    if kind == "people":
        return {"universe": universe}
    return {"name": name}


def write_roster(client: Neo4jClient, universe: str, characters: tuple[RosterEntry, ...],
                 groups: tuple[RosterEntry, ...]) -> None:
    with client.session() as session:
        session.run("MERGE (:Universe {name:$universe})", universe=universe)
        session.run(
            "UNWIND $rows AS row MERGE (n:Character {name: row.name}) SET n.aliases=row.aliases "
            "WITH n MATCH (u:Universe {name:$universe}) MERGE (n)-[:IN_UNIVERSE]->(u)",
            universe=universe, rows=[{"name": c.name, "aliases": list(c.aliases)} for c in characters])
        session.run(
            "UNWIND $rows AS row MERGE (n:Group {name: row.name}) SET n.aliases=row.aliases "
            "WITH n MATCH (u:Universe {name:$universe}) MERGE (n)-[:IN_UNIVERSE]->(u)",
            universe=universe, rows=[{"name": g.name, "aliases": list(g.aliases)} for g in groups])
        session.run("MERGE (:People {universe:$universe})", universe=universe)


class FactWriter:
    def __init__(self, client: Neo4jClient, embedder: Embedder, universe: str, run_id: str, model: str,
                prompt_version: str, characters: tuple[RosterEntry, ...], groups: tuple[RosterEntry, ...]):
        self._client = client
        self._embedder = embedder
        self._universe = universe
        self._run_id = run_id
        self._model = model
        self._prompt_version = prompt_version
        self._lookup = build_lookup(characters, groups)

    def write_one(self, fact: ParseReply, variant: str, simple_sentence_id: str, source_sentence_id: int,
                 section: str, source_sentence: str) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        if fact.kind == "property":
            self._write_property(fact, variant, simple_sentence_id, source_sentence_id, section,
                                 source_sentence, created_at)
        else:
            self._write_edge(fact, variant, simple_sentence_id, source_sentence_id, section,
                             source_sentence, created_at)

    def _write_edge(self, f: ParseReply, variant, simple_id, source_id, section, source_sentence, created_at):
        action_vec = self._embed(f.predicate) if f.predicate else []
        desc_vec = self._embed(f.description) if f.description else []
        concept_vec = self._embed(f.target) if f.target_type == "concept" and f.target else []
        subj_key = _node_key(f.subject_type, self._universe, f.subject)
        tgt_key = _node_key(f.target_type or "concept", self._universe, f.target or "unspecified")
        key_src = f"{f.subject}|{f.predicate}|{f.target}|{simple_id}|{variant}|{self._run_id}"
        row = dict(
            subj_key=subj_key, tgt_key=tgt_key, predicate=f.predicate, predicate_raw=f.predicate_raw,
            predicate_embedding=action_vec, via=f.via, description=f.description,
            description_embedding=desc_vec, modality=f.modality, negated=f.negated, mutual=f.mutual,
            frequency=f.frequency, degree=f.degree, certainty=f.certainty, former=f.former,
            simple_sentence_id=simple_id, source_sentence_id=source_id, section=section, variant=variant,
            run_id=self._run_id, model=self._model, prompt_version=self._prompt_version,
            created_at=created_at, source_sentence=source_sentence,
            edge_key=hashlib.sha1(key_src.encode("utf-8")).hexdigest())
        set_concept = "SET o.embedding = row.concept_embedding " if f.target_type == "concept" else ""
        row["concept_embedding"] = concept_vec
        sl, tl = _LABEL[f.subject_type], _LABEL.get(f.target_type or "concept", "Concept")
        # Any Character/Group node created here (not just ones pre-registered by write_roster) gets its
        # IN_UNIVERSE tie too -- the edge is the only record of universe, so it can never be skipped.
        tie_s = f"MERGE (s)-[:IN_UNIVERSE]->(univ) " if sl in ("Character", "Group") else ""
        tie_o = f"MERGE (o)-[:IN_UNIVERSE]->(univ) " if tl in ("Character", "Group") else ""
        cypher = (
            f"MERGE (univ:Universe {{name: $universe}}) "
            f"WITH univ "
            f"UNWIND $rows AS row "
            f"MERGE (s:{sl} {{{', '.join(f'{k}: row.subj_key.{k}' for k in subj_key)}}}) "
            f"MERGE (o:{tl} {{{', '.join(f'{k}: row.tgt_key.{k}' for k in tgt_key)}}}) "
            f"{set_concept}{tie_s}{tie_o}"
            f"MERGE (s)-[r:EDGE {{edge_key: row.edge_key}}]->(o) "
            f"SET r.predicate=row.predicate, r.predicate_raw=row.predicate_raw, "
            f"r.predicate_embedding=row.predicate_embedding, r.via=row.via, r.description=row.description, "
            f"r.description_embedding=row.description_embedding, r.modality=row.modality, "
            f"r.negated=row.negated, r.mutual=row.mutual, r.frequency=row.frequency, r.degree=row.degree, "
            f"r.certainty=row.certainty, r.former=row.former, r.simple_sentence_id=row.simple_sentence_id, "
            f"r.source_sentence_id=row.source_sentence_id, r.section=row.section, r.variant=row.variant, "
            f"r.run_id=row.run_id, r.model=row.model, r.prompt_version=row.prompt_version, "
            f"r.created_at=row.created_at, r.source_sentence=row.source_sentence"
        )
        with self._client.session() as session:
            session.run(cypher, rows=[row], universe=self._universe)

    def _write_property(self, f: ParseReply, variant, simple_id, source_id, section, source_sentence, created_at):
        prop_vec = self._embed(f.property) if f.property else []
        subj_key = _node_key(f.subject_type, self._universe, f.subject)
        key_src = f"{f.subject}|{f.property}|{simple_id}|{variant}|{self._run_id}"
        row = dict(
            subj_key=subj_key, property=f.property, property_embedding=prop_vec, description=f.description,
            modality=f.modality, negated=f.negated, frequency=f.frequency, degree=f.degree,
            certainty=f.certainty, former=f.former, simple_sentence_id=simple_id, source_sentence_id=source_id,
            section=section, variant=variant, run_id=self._run_id, model=self._model,
            prompt_version=self._prompt_version, created_at=created_at, source_sentence=source_sentence,
            edge_key=hashlib.sha1(key_src.encode("utf-8")).hexdigest())
        sl = _LABEL[f.subject_type]
        tie_s = f"MERGE (s)-[:IN_UNIVERSE]->(univ) " if sl in ("Character", "Group") else ""
        cypher = (
            f"MERGE (univ:Universe {{name: $universe}}) "
            f"WITH univ "
            f"UNWIND $rows AS row "
            f"MERGE (s:{sl} {{{', '.join(f'{k}: row.subj_key.{k}' for k in subj_key)}}}) "
            f"MERGE (p:Concept {{name: row.property}}) SET p.embedding = row.property_embedding "
            f"{tie_s}"
            f"MERGE (s)-[r:HAS_PROPERTY {{edge_key: row.edge_key}}]->(p) "
            f"SET r.description=row.description, r.modality=row.modality, r.negated=row.negated, "
            f"r.frequency=row.frequency, r.degree=row.degree, r.certainty=row.certainty, r.former=row.former, "
            f"r.simple_sentence_id=row.simple_sentence_id, r.source_sentence_id=row.source_sentence_id, "
            f"r.section=row.section, r.variant=row.variant, r.run_id=row.run_id, r.model=row.model, "
            f"r.prompt_version=row.prompt_version, r.created_at=row.created_at, "
            f"r.source_sentence=row.source_sentence"
        )
        with self._client.session() as session:
            session.run(cypher, rows=[row], universe=self._universe)

    def _embed(self, word: str) -> list[float]:
        vecs = self._embedder.embed([word], is_query=False)
        return [float(x) for x in vecs[0]] if len(vecs) else []

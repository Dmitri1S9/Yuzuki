"""Методы извлечения. Каждый: (paragraphs, roster, llm, owner) -> list[dict] — по записи на абзац.

Запись абзаца: {"id", "relations": [{"name", "canonical", "type", "affinity", "evidence"}], "traits": [...]}.
`name` — что сказала модель, `canonical` — к чему это разрешилось по ростеру (None = имени нет в словаре).

  rel_free      M0  базовая линия = текущий план владельца: "перечисли связи одним словом", имена пишет модель.
  rel_anchored  M1  кандидаты находит КОД (ростер + заголовок секции), схема = объект с ключом на каждого
                    кандидата (grammar-constrained). Модель не может назвать имя вне списка и не может пропустить.
  rel_pairwise  M2  отдельный короткий вопрос на каждую пару (owner, X); абзац — общий кэшируемый префикс.
  rel_verify    M3  M1 + проверка каждой найденной связи вопросом да/нет "следует ли из абзаца ..." (NLI-шаблоны
                    Sainz et al. 2021; extract-then-verify как CoVe). Верификатор не видит ответ M1, только утверждение.
  traits_lexicon T0 без LLM: совпадения с лексиконом маркеров Big Five/HEXACO (research/exp/lexicon.yaml).
  traits_llm     T1 модель выписывает дословные фрагменты-черты, полюс из 12 и статус (actual/apparent/negated/
                    other_character) — буквальность решает классификация, а не пост-фильтр.
"""
import re
from pathlib import Path

import yaml

from .pages import Paragraph
from .roster import Roster
from .taxonomy import AFFINITY, REL_TYPE_ENUM, REL_TYPES, TRAIT_POLES, TRAIT_STATUS, UNSPECIFIED

LEXICON_PATH = Path(__file__).resolve().parent / "lexicon.yaml"


def _type_guide() -> str:
    lines = [f"- {k}: {v[0]}" for k, v in REL_TYPES.items()]
    lines.append(f"- {UNSPECIFIED}: they interact, but the paragraph does not say what kind of relationship it is")
    return "\n".join(lines)


def _header(owner: str, p: Paragraph) -> str:
    return f'Wiki page about {owner}. Page: "{p.page}". Section: "{p.section}".'


# ---------------------------------------------------------------- M0
def rel_free(paragraphs, roster: Roster, llm, owner: str) -> list[dict]:
    schema = {"type": "object", "properties": {"relations": {"type": "array", "items": {
        "type": "object", "properties": {"name": {"type": "string"}, "relation": {"type": "string"}},
        "required": ["name", "relation"]}}}, "required": ["relations"]}
    out = []
    for p in paragraphs:
        system = (f"You read paragraphs of the wiki page about {owner}. List every person or group that {owner} "
                  f"has a connection with in the paragraph. For each give the full name and ONE neutral word for "
                  f"the kind of connection.")
        ans = llm.chat(system, f"{_header(owner, p)}\n\n{p.text}", schema) or {}
        rels = []
        for r in ans.get("relations") or []:
            word = str(r.get("relation", "")).strip().lower()
            rels.append({"name": r.get("name", ""), "canonical": roster.resolve(str(r.get("name", ""))),
                         "type": word if word in REL_TYPES else UNSPECIFIED, "raw_type": word,
                         "affinity": None, "evidence": None})
        out.append({"id": p.id, "relations": rels})
    return out


# ---------------------------------------------------------------- candidates (code, not model)
def candidates(p: Paragraph, roster: Roster, owner: str) -> list[str]:
    """Упомянутые в абзаце сущности + сущности из заголовка секции ("Denki Kaminari", "Kyotoku and Mika Jiro").
    На подстраницах Relationships заголовок секции и есть собеседник ("the two ..." без имени)."""
    names = roster.mentions(p.section) if p.page.endswith("/Relationships") else []
    names += [n for n in roster.mentions(p.text) if n not in names]
    return [n for n in names if n != owner]


def _pair_props() -> dict:
    return {"evidence": {"type": "string", "maxLength": 200}, "linked": {"type": "boolean"},
            "type": {"type": "string", "enum": REL_TYPE_ENUM}, "affinity": {"type": "string", "enum": AFFINITY}}


def _rel_system(owner: str) -> str:
    """Постоянная часть промпта (одинакова для всех абзацев страницы) -> идёт первой и кэшируется."""
    return (f"You read paragraphs of the wiki page about {owner}. "
            f"Names in the paragraph are marked as [mention](Canonical Name).\n"
            f"Decide, using ONLY this paragraph, whether {owner} personally interacts with or has a stated "
            f"relationship with the given entity. Being mentioned in the same sentence is not enough.\n"
            f"evidence: copy the shortest exact phrase from the paragraph that shows it (empty if none).\n"
            f"type (relationship from {owner}'s side):\n{_type_guide()}\n"
            f"affinity: positive / neutral / negative attitude between them in this paragraph.")


# ---------------------------------------------------------------- B0 (без LLM)
def rel_cooccur(paragraphs, roster: Roster, llm, owner: str) -> list[dict]:
    """Нижняя граница: каждый кандидат абзаца = связь. Recall этого метода = потолок для M1–M3."""
    return [{"id": p.id, "candidates": (c := candidates(p, roster, owner)),
             "relations": [{"name": n, "canonical": n, "type": UNSPECIFIED, "affinity": "neutral"} for n in c]}
            for p in paragraphs]


# ---------------------------------------------------------------- M1
def rel_anchored(paragraphs, roster: Roster, llm, owner: str) -> list[dict]:
    out = []
    for p in paragraphs:
        cands = candidates(p, roster, owner)
        rels = []
        if cands:
            props = {"type": "object", "properties": _pair_props(), "required": list(_pair_props())}
            schema = {"type": "object", "properties": {c: props for c in cands}, "required": cands,
                      "additionalProperties": False}
            ans = llm.chat(_rel_system(owner) + "\nAnswer for EVERY entity listed in the schema.",
                           f"{_header(owner, p)}\nParagraph:\n{roster.mark(p.text)}\n\nEntities: {', '.join(cands)}",
                           schema,
                           num_predict=120 * len(cands) + 50) or {}
            for c in cands:
                a = ans.get(c) or {}
                if a.get("linked"):
                    rels.append({"name": c, "canonical": c, "type": a.get("type", UNSPECIFIED),
                                 "affinity": a.get("affinity"), "evidence": a.get("evidence")})
        out.append({"id": p.id, "candidates": cands, "relations": rels})
    return out


# ---------------------------------------------------------------- M2
def rel_pairwise(paragraphs, roster: Roster, llm, owner: str) -> list[dict]:
    schema = {"type": "object", "properties": _pair_props(), "required": list(_pair_props())}
    out = []
    for p in paragraphs:
        cands = candidates(p, roster, owner)
        system = _rel_system(owner)
        para = f"{_header(owner, p)}\nParagraph:\n{roster.mark(p.text)}"  # общий префикс между кандидатами -> KV-кэш
        rels = []
        for c in cands:
            a = llm.chat(system, f"{para}\n\nEntity: {c}", schema, num_predict=150) or {}
            if a.get("linked"):
                rels.append({"name": c, "canonical": c, "type": a.get("type", UNSPECIFIED),
                             "affinity": a.get("affinity"), "evidence": a.get("evidence")})
        out.append({"id": p.id, "candidates": cands, "relations": rels})
    return out


# ---------------------------------------------------------------- M3
_YESNO = {"type": "object", "properties": {"answer": {"type": "string", "enum": ["yes", "no"]}},
          "required": ["answer"]}


def rel_verify(paragraphs, roster: Roster, llm, owner: str, drafts: dict[str, dict] | None = None) -> list[dict]:
    """drafts: готовые ответы M1 по id абзаца (из rel_anchored.jsonl) — чтобы не считать M1 второй раз."""
    todo = [p for p in paragraphs if not drafts or p.id not in drafts]
    draft = {**(drafts or {}), **{r["id"]: r for r in rel_anchored(todo, roster, llm, owner)}}
    out = []
    for p in paragraphs:
        rec = draft[p.id]
        system = "Answer strictly from the paragraph. If the paragraph does not clearly say it, answer no."
        para = f"Paragraph:\n{roster.mark(p.text)}"
        kept = []
        for r in rec["relations"]:
            stmt = f"The paragraph shows {owner} directly interacting with, acting on, or relating to {r['canonical']}."
            if (llm.chat(system, f"{para}\n\nStatement: {stmt}\nIs the statement true?", _YESNO, 10) or {}).get(
                    "answer") != "yes":
                continue
            if r["type"] in REL_TYPES:
                stmt = REL_TYPES[r["type"]][2].format(a=owner, b=r["canonical"])
                if (llm.chat(system, f"{para}\n\nStatement: {stmt}\nIs the statement true?", _YESNO, 10) or {}).get(
                        "answer") != "yes":
                    r = {**r, "type": UNSPECIFIED}
            kept.append(r)
        out.append({**rec, "relations": kept})
    return out


# ---------------------------------------------------------------- T0
def load_lexicon(path: Path = LEXICON_PATH) -> dict[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {w.lower(): pole for pole, words in data["poles"].items() for w in words}


def traits_lexicon(paragraphs, roster: Roster, llm, owner: str) -> list[dict]:
    lex = load_lexicon()
    pat = re.compile(r"\b(" + "|".join(sorted(map(re.escape, lex), key=len, reverse=True)) + r")\b", re.I)
    return [{"id": p.id, "traits": [{"span": m.group(0), "pole": lex[m.group(0).lower()], "status": "actual"}
                                    for m in pat.finditer(p.text)]} for p in paragraphs]


# ---------------------------------------------------------------- T1
def traits_llm(paragraphs, roster: Roster, llm, owner: str) -> list[dict]:
    schema = {"type": "object", "properties": {"traits": {"type": "array", "maxItems": 30, "items": {
        "type": "object", "properties": {
            "span": {"type": "string", "maxLength": 60},
            "pole": {"type": "string", "enum": list(TRAIT_POLES)},
            "status": {"type": "string", "enum": TRAIT_STATUS}},
        "required": ["span", "pole", "status"]}}}, "required": ["traits"]}
    guide = "\n".join(f"- {k}: {v}" for k, v in TRAIT_POLES.items())
    out = []
    for p in paragraphs:
        system = (f"You read the wiki page about {owner}.\nExtract every personality trait, habit of behaviour or emotional tendency "
                  f"the paragraph attributes to a person. span: copy 1-4 words EXACTLY from the paragraph.\n"
                  f"pole (Big Five + HEXACO honesty-humility):\n{guide}\n"
                  f"status: actual = {owner} really has it; apparent = only seems so / others think so; "
                  f"negated = the text says {owner} does NOT have it; other_character = it describes someone else.")
        ans = llm.chat(system, f"{_header(owner, p)}\n\n{p.text}", schema, num_predict=900) or {}
        out.append({"id": p.id, "traits": list(ans.get("traits") or [])})
    return out


METHODS = {"rel_cooccur": rel_cooccur, "rel_free": rel_free, "rel_anchored": rel_anchored, "rel_pairwise": rel_pairwise,
           "rel_verify": rel_verify, "traits_lexicon": traits_lexicon, "traits_llm": traits_llm}


# ---------------------------------------------------------------- ordinals (без эталона; см. ordinals.py)
def comparisons(paragraphs, roster: Roster, llm, owner: str) -> list[dict]:
    """Попарные исходы боёв/сравнений между кандидатами абзаца. Имена — только enum из кода."""
    out = []
    for p in paragraphs:
        cands = [n for n in roster.mentions(p.text) if roster.kind(n) == "character"]
        if len(cands) < 2:
            continue
        item = {"type": "object", "properties": {
            "evidence": {"type": "string", "maxLength": 200},
            "winner": {"type": "string", "enum": cands}, "loser": {"type": "string", "enum": cands},
            "outcome": {"type": "string", "enum": ["defeated", "stronger_than", "draw"]}},
            "required": ["evidence", "winner", "loser", "outcome"]}
        schema = {"type": "object", "properties": {"results": {"type": "array", "maxItems": 10, "items": item}},
                  "required": ["results"]}
        system = (f"{_header(owner, p)}\nList only fights or explicit power comparisons STATED in the paragraph "
                  f"between two of these characters: {', '.join(cands)}. defeated = one beat the other; "
                  f"stronger_than = text says one is stronger; draw = neither won. Empty list if none.")
        ans = llm.chat(system, roster.mark(p.text), schema, num_predict=600) or {}
        res = [r for r in ans.get("results") or [] if r.get("winner") != r.get("loser")]
        out.append({"id": p.id, "comparisons": res})
    return out


# ---------------------------------------------------------------- T2
_TRAIT_STOP = set("""a an the and or but of to in on at for with by from as is was were be been being are it its he she him
her his hers they them their this that these those who whom which what when where while also very quite so too not no
has have had do does did can could would should will may might must than then there here into onto over under after
before during about up down out off again further once all any both each few more most other some such only own same
just even still often usually sometimes later much many one two""".split())


def span_candidates(text: str) -> list[str]:
    """Слова и пары соседних слов абзаца (без стоп-слов на краях) — единственные допустимые span'ы."""
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    out: list[str] = []
    for i, w in enumerate(words):
        if w.lower() not in _TRAIT_STOP and len(w) > 2:
            out.append(w.lower())
        if i + 1 < len(words):
            a, b = words[i], words[i + 1]
            if a.lower() not in _TRAIT_STOP and b.lower() not in _TRAIT_STOP:
                out.append(f"{a.lower()} {b.lower()}")
    return list(dict.fromkeys(out))


def traits_anchored(paragraphs, roster: Roster, llm, owner: str) -> list[dict]:
    """T2: как T1, но span — enum из слов/биграмм абзаца (выдумать фрагмент нельзя); дубликаты убирает код."""
    guide = "\n".join(f"- {k}: {v}" for k, v in TRAIT_POLES.items())
    system = (f"You read the wiki page about {owner}.\nExtract the personality traits, habits of behaviour and "
              f"emotional tendencies the paragraph attributes to a person. Each trait ONCE. span: the word or two-word "
              f"phrase from the paragraph that names the trait (an adjective or short noun phrase).\n"
              f"pole (Big Five + HEXACO honesty-humility):\n{guide}\n"
              f"status: actual = {owner} really has it; apparent = only seems so / others think so; "
              f"negated = the text says {owner} does NOT have it; other_character = it describes someone else.\n"
              f"If the paragraph describes no traits, return an empty list.")
    out = []
    for p in paragraphs:
        cands = span_candidates(p.text)
        schema = {"type": "object", "properties": {"traits": {"type": "array", "maxItems": 15, "items": {
            "type": "object", "properties": {
                "span": {"type": "string", "enum": cands},
                "pole": {"type": "string", "enum": list(TRAIT_POLES)},
                "status": {"type": "string", "enum": TRAIT_STATUS}},
            "required": ["span", "pole", "status"]}}}, "required": ["traits"]}
        ans = llm.chat(system, f"{_header(owner, p)}\n\n{p.text}", schema, num_predict=500) or {}
        seen, traits = set(), []
        for t in ans.get("traits") or []:
            if t.get("span") not in seen:
                seen.add(t.get("span"))
                traits.append(t)
        out.append({"id": p.id, "traits": traits})
    return out


METHODS["traits_anchored"] = traits_anchored


# ---------------------------------------------------------------- T3
def traits_verify(paragraphs, roster: Roster, llm, owner: str, drafts: dict[str, dict] | None = None) -> list[dict]:
    """T3: T2 + вопрос да/нет на каждую найденную черту (верификатор видит только абзац и утверждение)."""
    todo = [p for p in paragraphs if not drafts or p.id not in drafts]
    draft = {**(drafts or {}), **{r["id"]: r for r in traits_anchored(todo, roster, llm, owner)}}
    system = ("Answer strictly from the paragraph. A personality trait is a lasting quality of character, temperament "
              "or typical behaviour (e.g. shy, kind, reckless) - not an action, event, goal or object. "
              "If unsure, answer no.")
    out = []
    for p in paragraphs:
        kept = []
        for t in draft[p.id]["traits"]:
            if t.get("status") != "actual":
                kept.append(t)
                continue
            q = (f"Paragraph:\n{p.text}\n\nStatement: In this paragraph, \"{t['span']}\" describes a personality trait "
                 f"or typical behaviour of {owner}.\nIs the statement true?")
            if (llm.chat(system, q, _YESNO, 10) or {}).get("answer") == "yes":
                kept.append(t)
        out.append({"id": p.id, "traits": kept})
    return out


METHODS["traits_verify"] = traits_verify

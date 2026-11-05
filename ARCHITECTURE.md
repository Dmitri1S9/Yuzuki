# ARCHITECTURE

Текущий курс: **вики-дамп → извлечение кодом + локальной моделью → граф (Neo4j) → GNN**.
Всё, что от этого курса отошло, лежит в `legacy/` (см. `legacy/README.md`).

## Поток данных (рекомендованный, см. research/REPORT.md)

```
Fandom XML dump
  │  src/wiki/dump_reader.py, wikitext_cleaner.py
  ▼
страницы → секции → абзацы (id = "page|section|idx")          research/samples/extract_pages.py
  │
  ├─ ростер вселенной КОДОМ: категории + редиректы + подписи [[ссылок]]   research/samples/build_roster.py
  │
  ├─ кандидаты абзаца = упоминания по ростеру (+ заголовок секции на /Relationships)  research/exp/roster.py
  │     → co-occurrence: «связь возможна» (без модели)
  ├─ LLM выбирает из закрытых списков (JSON Schema enum → GBNF в llama.cpp):
  │     для каждого кандидата: linked? type? affinity? evidence          research/exp/methods.py: rel_anchored
  │     черты: дословный фрагмент + полюс Big Five/HEXACO + статус         methods.py: traits_llm
  │     бои/сравнения: winner/loser ∈ кандидаты                            methods.py: comparisons
  ├─ (опц.) проверка да/нет каждой найденной связи                         methods.py: rel_verify
  ▼
записи (src/graph_store/store.py: EntityRecord, RelationRecord, TraitRecord, MembershipRecord)
  ▼
Neo4j  ← слой пишется руками (src/graph_store — заглушка)
  ▼
агрегаты: тип связи по странице, тиры (research/exp/ratings.py: Bradley–Terry–Davidson по компонентам)
```

Принцип: **модель никогда не генерирует имя и никогда не придумывает категорию** — оба берутся из списков,
которые построил код (ростер) или которые взяты из литературы (`research/exp/taxonomy.py`).

## Предложение по модели графа (для ручной реализации)

- `(:Universe {name})`, `(:Character {universe, name, aliases})`, `(:Group {universe, name})` —
  ключ уникальности `(universe, name)`, не `name` (в legacy extract_v3 был глобальный UNIQUE по имени — коллизии между вселенными).
- `(c)-[:MEMBER_OF]->(g)` — только факт членства.
- `(a)-[:RELATES {type, affinity, evidence, paragraph_id, method}]->(b)` — по ребру на абзац (наблюдение);
  агрегат по паре считается запросом или отдельным ребром `:RELATION_SUMMARY`.
- `(c)-[:HAS_TRAIT {span, paragraph_id, method}]->(:TraitPole {code: "A-"})` и
  `(:RelType {name: "mentor"})` — **общие узлы-абстракции**, которые и связывают вселенные: они из закрытых
  таксономий, поэтому одинаковы во всех вселенных без «родственников в ≥2 вселенных».
- `(a)-[:BEATS {outcome, evidence, paragraph_id}]->(b)` — сырьё для тиров.
- Провенанс (`method`, `paragraph_id`, модель) на каждом ребре: разные части данных собираются разными методами
  (инфобокс, co-occurrence, LLM) и должны сравниваться/перевзвешиваться, а не перезаписывать друг друга.

## Конвенции

- `src/wiki/*` — атомарные модули без бизнес-логики и логирования.
- Эксперименты (`research/exp`) — только stdlib + PyYAML, чтобы запускаться одной командой на ноутбуке.
- Каждый метод извлечения: `(paragraphs, roster, llm, owner) -> list[record]`; метрики — `research/exp/score.py`
  против `research/gold/*.yaml`.
- Тесты: `pytest -q tests` (живой код), `cd legacy && pytest tests/proto_wiki` (legacy).

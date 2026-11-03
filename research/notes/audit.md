> Аудит выполнен ДО переноса в legacy/: пути `src/<x>` ниже теперь `legacy/src/<x>` (кроме `src/wiki`, скопированного из `extract_v3/external`). Исправленное в этой ветке отмечено в research/REPORT.md §Аудит.

# Yuzuki read-only audit (HEAD 79cab25, 2026-11-04 "small update")

Nothing in the repo was modified. Tests ran in a scratchpad venv (`-p no:cacheprovider`); the `__pycache__` dirs it created were deleted. `git status` shows only `?? research/` (untracked, created 2026-11-03 23:06 by someone else, not this audit; contains `gold/traits.yaml`, `gold/kyoka_jiro.relations.yaml`, and empty `exp/ runs/ samples/`).

## 0. Git timeline (the evidence base)

| commit | date | what |
|---|---|---|
| eb4bc70..4660d4a | 05-12..09-02 | API-model collection, kappa, groups |
| edeaca3 | 09-12 | reorganised into `src/{api,domain,infra,repository,services,shared}`; added PIPELINE.md, ARCHITECTURE.md, run_*.sh |
| 8fa6c47 | 09-22 | "tree architecture", AniList/images, DB consensus, Celery; `src/experiments/compare_*.py` |
| d9eadf8 | 09-29 | `src/graph_extract` (v2 ACTION/DESCRIBED_AS -> Neo4j) |
| 90e5839 | 09-30 | renamed graph_extract to `src/extract_v3`, added `extract_v3/external/*`. Says it drops `yuzuki_local`, but **yuzuki_local was never committed on master**. Says snapshot is on branch `wip-full-snapshot`, but **that branch is not local or on origin** (`git ls-remote` shows only master; local branches: master, claude/new-session-akcnem). **At 90e5839, extract_v3 was broken**: rewriter/parser_llm/neo4j_schema/text_prep still imported `yuzuki_local.*`. 79cab25 fixed those imports. |
| 79cab25 | 11-04 | catch-all dump, 148 files. **Deleted ARCHITECTURE.md and PIPELINE.md.** Added `src/proto_wiki`, `tests/proto_wiki`, `tests/yuzuki_local`, `src/experiments/jiro_flags_local`, extract_v3 checkpoints and test_env, and the neo4j service in compose. Deleted compare_*.py and tempCodeRunnerFile.R. Also edited legacy code: api, consensus, collection, gemini client, prompts. |

## 1. Live/dead map

Categories: **LIVE** (wiki/local-LLM/graph), **LEG-API** (Gemini/Grok collection), **LEG-EXP** (abandoned experiment), **BROKEN**.

### src/
| path | what | cat | evidence |
|---|---|---|---|
| `src/extract_v3/` | Current pipeline: dump, cleaned sentences, LLM rewrite to simple sentences, LLM parse to an EDGE/PROPERTY fact, Neo4j | **LIVE (current)** | Newest graph work: created 09-30, updated 11-04 (multi-page, model swap, test_env). Self-contained: only relative imports, no `src.*` imports. Smoke-imports OK except `neo4j` (no pip package here). |
| `src/extract_v3/external/` | dump_reader, wikitext_cleaner, ollama, embedder, neo4j_client | **LIVE (reusable infra)** | Imported by extract_v3 and by `experiments/jiro_flags_local/run.py` |
| `src/extract_v3/test_env/` | static HTML plus stdlib proxy for poking Ollama by hand, `data.json` (285 paragraphs and full context) | LIVE-tooling | Added 11-04. Nothing in the repo generates data.json. |
| `src/extract_v3/.pass1_jiro-v3.json`, `.checkpoint_jiro-v3.json` | run caches (459 KB, 58 KB) | junk (committed run state) | See section 3 |
| `src/proto_wiki/` | Older one-character prototype: coref, closed-vocab triples, pyvis graph, flags/ordinals judged from wiki text | **LEG-EXP** (superseded by extract_v3) | Committed 11-04 but older in design. extract_v3's `external/ollama.py` and `wikitext_cleaner.py` are evolved copies of `proto_wiki/infra/ollama_client.py` and `services/parsing/text_loader.parse_wikitext` (adds PromptTooLong/CallMetrics, `ruby` template, more skip sections). Docstrings say "existing Yuzuki pipeline untouched" and cite the deleted ARCHITECTURE.md. Does step-3 flags/ordinals (abandoned). No Neo4j. Only tested package (36/36 pass). |
| `src/experiments/jiro_flags_local/` | flags-on-local-model experiment: 64 flags × 5 MHA characters, yes/no/no_data plus quote check | **LEG-EXP** (abandoned flags) | Added 11-04. Its docstring says "copied from the old yuzuki_local (wip-full-snapshot)". Depends on extract_v3.external. Only pass 1 results exist, so kappa.py cannot run. |
| `src/experiments/__init__.py` | empty | LEG-EXP shell | compare_*.py deleted in 79cab25 |
| `src/api/` | FastAPI that DCS calls (confirm/library/media/pipeline/relations/universes) | LEG-API | Imports domain, repository, services, shared, infra. Dockerfile CMD runs uvicorn `src.api.main:app` |
| `src/domain/` | Character/Group/Relation/Universe, `parameters.json` (6 ordinals, 51 flags, profile) | LEG-API, but `parameters.json` is **read by proto_wiki** | see section 2 |
| `src/infra/ai_clients/` | Gemini, X/Grok, Cerebras clients and response schemas | LEG-API | `CerebrasClient` and `XClient` are imported nowhere (dead). cerebras docstring cites deleted `experiments/compare_models.py`. |
| `src/infra/prompts/` | Jinja templates for Stages 1-3 | LEG-API, but **templates are read by proto_wiki** (tier descriptions) | section 2 |
| `src/infra/{celery_app,dcs_client,token_usage,exceptions}.py`, `infra/settings/` | Celery, DCS push, Postgres token log, Redis cache, pydantic settings | LEG-API | |
| `src/repository/` | psycopg2 repositories, `schema/init.sql` and 12 migrations (Postgres `archangel`) | LEG-API | init.sql is mounted by docker-compose `db` |
| `src/services/collection/{cast,relations,features}` | Stage 1 cast, Stage 3 relations, Stage 2 flags+ordinals | LEG-API | run by run_pipeline.sh and run_stage2.sh |
| `src/services/consensus/` | kappa/maximin consensus for flags and ordinals | LEG-API | |
| `src/services/graph/` | pyvis render of Postgres relations | LEG-API | `python -m src.services.graph.main` |
| `src/services/pipeline_tasks.py` | Celery task that launches a stage as a subprocess | LEG-API | |
| `src/shared/` | naming/slugify, run paths, decorators, media_url | LEG-API | Used only by legacy and the run_*.sh scripts. proto_wiki has its own decorator copy. |
| `src/__init__.py` | package marker | — | needed for `python -m src.…` |
| (missing) `src/yuzuki_local/` | — | **absent** | Not in repo or history. Only `tests/yuzuki_local` refers to it. |

### tests/
| path | cat | status |
|---|---|---|
| `tests/proto_wiki/` (5 files) | LEG-EXP tests | 36/36 pass. `test_text_loader.py:89-94` reads the legacy `src/domain/parameters.json` (expects 6 ordinals, 51 flags). |
| `tests/yuzuki_local/` (7 files) | **BROKEN/orphan** | Imports `yuzuki_local.{entities,workers,external}`. That module is not in the repo or any reachable commit; 90e5839 says it was dropped. Collection fails, which aborts the whole `pytest tests/` run. One file, `test_ollama_client.py`, passes 5/5 if repointed to `extract_v3.external.ollama` (same API). `test_context_builder.py` uses DumpReader/WikiTextCleaner, which also exist in extract_v3.external, but also needs the gone `ContextBuilder`/`ContextSettings`. |
| no tests for extract_v3 | — | gap |

### root
| file | what | cat | evidence |
|---|---|---|---|
| `run_pipeline.sh` | Stage 1 -> Stage 3 -> Stage 2 via docker compose + conda | LEG-API | last touched 09-22 |
| `run_stage2.sh` | features + `Rscript kappa_analysis.R` | LEG-API | 09-12 |
| `kappa_analysis.R` | Cohen's kappa over `run/pass{1,2,3}_<slug>.csv` | LEG-API | 09-12 |
| `analyse.yml` | conda env (python 3.12, celery, fastapi, google-genai, xai_sdk, psycopg2, redis, opencv…) | LEG-API | **Lacks** neo4j, fastembed, mwparserfromhell, networkx, pyyaml, so it cannot run extract_v3 or proto_wiki |
| `Dockerfile` | mambaforge image, CMD uvicorn API | LEG-API | 09-22 |
| `docker-compose.yaml` | db (pg14 :5439), **neo4j:5 (:7474/:7687)**, analyse_service, celery_worker, redis, r_analysis | mixed: the `neo4j` service (lines 16-26) is **LIVE**, the rest is LEG-API | neo4j block added 11-04 |
| `Yuzuki.code-workspace` | VS Code folder "." | neutral/junk | 05-12 |
| `README.md` | Russian docs of the Gemini/Postgres 4-stage pipeline, plus a personal essay | LEG-API, stale | Links PIPELINE.md and ARCHITECTURE.md (lines 20-21, 42); **both deleted in 79cab25**. Image `wp5522224-…png` (line 8) **does not exist**. No mention of extract_v3, Ollama or Neo4j. |
| `.gitignore` | | — | line 66 ignores `.dockerignore`, yet `.dockerignore` is tracked. Run caches `.pass1_*` and `.checkpoint_*` are not ignored. |
| `.dockerignore` | `    .env` (leading spaces) | — | Probably OK (Docker trims patterns), but nothing else is excluded, so `COPY . /app` copies `.git`, the caches and `research/`. |
| `CLAUDE.md` | agent guidelines | neutral | |

## 2. Import/data edges between live and legacy (what breaks if legacy moves to `legacy/`)

**Python import edges (AST scan of all of src/):**
- `extract_v3` imports only `extract_v3.*` (30 relative imports). **0 edges** to `src.infra`, `src.shared`, `src.domain` or anything legacy.
- `proto_wiki` imports only `proto_wiki.*` (41 relative imports). **0 Python edges** to legacy.
- Legacy has no imports of `extract_v3`, `proto_wiki` or `experiments`. Legacy-internal imports all resolve (no broken `src.*` imports).
- `src/experiments/jiro_flags_local/run.py:18` does `sys.path.insert(0, HERE.parent.parent)` (= `src/`). Lines 61-62 then do `from extract_v3.external.dump_reader import DumpReader` and `from extract_v3.external.wikitext_cleaner import WikiTextCleaner`. This is an experiment-to-live edge. **It breaks if jiro_flags_local moves** to `legacy/…`, because `HERE.parent.parent` would no longer be `src/`. The import is lazy, used only when `contexts/<char>.txt` is missing; the 5 contexts are committed.

**Path/data edges (not imports, so they break silently):**
| from | to | where |
|---|---|---|
| proto_wiki | `src/domain/parameters.json` | `src/proto_wiki/cli.py:15` `DEFAULT_PARAMS = parents[1]/"domain"/"parameters.json"` |
| proto_wiki | `src/infra/prompts/templates/*.j2` | `src/proto_wiki/services/parsing/params_loader.py:37` `templates_dir = path.parent.parent/"infra"/"prompts"/"templates"`, relative to the params file. If moved, tier descriptions silently become `{}` (`_tier_descriptions` returns `{}` when the file is missing). |
| tests/proto_wiki | `src/domain/parameters.json` | `tests/proto_wiki/test_text_loader.py:91` |
| extract_v3 | repo-root `.env` | `src/extract_v3/settings.py:61` `PACKAGE_DIR.parent.parent/".env"` (depth-sensitive; moving extract_v3 changes which .env it reads) |
| extract_v3 | its own dir for caches and REPORT.md | `run_jiro.py:28-31,142` (writes into the package dir) |
| run_pipeline.sh / run_stage2.sh | `src.shared.naming`, `src.services.collection.*`, `kappa_analysis.R` at root | `run_pipeline.sh:9,22,32`, `run_stage2.sh:9,15,19` |
| docker-compose | `./src/repository/schema/init.sql`, `src.infra.celery_app` | `docker-compose.yaml:12,65` |
| Dockerfile | `src.api.main:app` | `Dockerfile:23` |
| legacy docstrings | ARCHITECTURE.md / PIPELINE.md (deleted) | `src/api/routes/library.py:8`, `src/infra/dcs_client.py:3`, `src/repository/relation_repository.py:38`, `src/services/collection/{cast,relations,features}/main.py:4-5`, `cast/steps/persistence.py:4`, `relations/steps/merge.py:2`, `src/services/graph/main.py:4`, `src/shared/{paths,decorators}.py:2-5` |

**Verdict:** moving `src/{api,domain,infra,repository,services,shared}`, `run_*.sh`, `kappa_analysis.R`, `analyse.yml`, `Dockerfile` and most of compose together into `legacy/` breaks nothing in extract_v3. It breaks proto_wiki's default params and tier descriptions (and its test) unless proto_wiki moves too. jiro_flags_local breaks only on a cold context cache. The legacy code uses absolute `src.` imports, so it needs to keep a `src` package root (e.g. `legacy/src/...`) or a sed of `src.` to `legacy.src.`; the shell scripts, compose and Dockerfile need path updates.

## 3. Bugs and junk

### extract_v3
| file:line | issue | class |
|---|---|---|
| `neo4j_writer.py:53` + `resolve.py:30` | `self._lookup = build_lookup(...)` is built but **never used**, and `canonicalize()` is never called. LLM subject/target strings go into `MERGE (n:Character {name: …})` raw, so "Jiro", "Kyoka" and "Kyoka Jiro" become separate nodes, and targets like "the merchant" or "her father" become Character nodes. | obvious fix: apply `canonicalize` to subject/target in `_write_edge` and `_write_property` |
| `schemas.py:19` | `target_type: str` is free text, while `subject_type` is a Literal. `neo4j_writer.py:83` `_LABEL.get(f.target_type, "Concept")`: "Character" (capitalised), "location" and similar silently become Concept. | obvious fix: `Literal["character","group","people","concept"]` |
| `neo4j_writer.py:70` | an empty target makes a node named `"unspecified"`, labelled by target_type (so it can be a Character named "unspecified") | obvious |
| `run_jiro.py:61` and `run_jiro.py:114` | resume skips any cached key **whatever its status**, so `error` results in pass 1 and 2 are never retried | needs owner decision (retry errors vs keep) |
| `run_jiro.py:30-31,56,108` | caches are keyed only by sentence id. Neither model nor prompt hash is in the key, but `prompt_version()` exists (`rewriter.py:43` is unused, parser's is stored only on edges). config changed the model to `hf.co/HauhauCS/Qwen3.5-9B-Uncensored…:Q8_0` in 79cab25, and the old cache would be reused silently. RUN_ID is hardcoded `"jiro-v3"` (`run_jiro.py:29`). | needs owner decision |
| `.pass1_jiro-v3.json` | 873 entries (0 HYPOTHETICAL, all ok). Ids 0-66 **lack the `page` key** (written by the pre-multipage code). Totals 2813 simple sentences. | junk / stale |
| `.checkpoint_jiro-v3.json` | 2166/2813 entries (source ids up to 689), i.e. **pass 2 is incomplete**. Graph state lives in a Neo4j instance outside the repo. | junk (committed run state; should be gitignored) |
| `config.yaml:7` | `dump_path: "/home/Di/Загрузки/bokunoheroacademia_pages_current.xml"`, a hardcoded absolute path | obvious (env/CLI override) |
| `config.yaml:13` | the model is an "Uncensored-Aggressive" HF finetune, not `qwen3.5:9b`. Docstrings (`run_jiro.py:4`, `parser_llm.py:1`) and `test_env/index.html:39` say qwen3.5:9b. | needs owner decision |
| `config.yaml:29` | comment cites `graph_extract/config.yaml`, which was deleted | obvious |
| `settings.py:26,47` + `external/ollama.py:100-101` | `think` is loaded from config but never passed; the client always sends `think: False`. `report.py:45` also hardcodes `think=false`. | obvious |
| `external/ollama.py:84-88` | retries on ValidationError at temperature 0 (deterministic) waste retries + sleeps | obvious-ish |
| `neo4j_writer.py:55,71` | the `variant` param (always "llm") is left over from the dropped spaCy variant but still baked into edge_key | dead code, owner decision (changing it changes edge keys) |
| `neo4j_schema.py:7-8` | `Character.name` and `Group.name` are globally UNIQUE. Two universes with the same character name will collide. | needs owner decision |
| `text_prep.py:46` | `drop_sections` matches exact heading only, not subsections (unlike WikiTextCleaner's skip_level) | obvious |
| `text_prep.py:10` | sentence split has no handling for Mr./Dr. (proto_wiki's `split_sentences` does) | obvious |
| `external/neo4j_client.py:1` | docstring cites a nonexistent `graph_db/` | trivial |
| `prompts/parse_prompt.j2` examples | property examples omit predicate/target/via/mutual and edge examples omit `property`, but `ParseReply` requires every field (Ollama `format` forces them, so it works, but the prompt and schema disagree) | owner decision |
| `test_env/data.json` | 252 KB derived data, no generator in repo | junk |
| no `requirements.txt` | needs pyyaml, pydantic, jinja2, httpx, mwparserfromhell, numpy, fastembed, neo4j | obvious |
| run entry | `python -m extract_v3.run_jiro` needs cwd=src (or `python -m src.extract_v3.run_jiro` from root); writes REPORT.md into the package | owner decision |

### proto_wiki
| file:line | issue | class |
|---|---|---|
| `cli.py:15`, `services/parsing/params_loader.py:37` | coupled to legacy `src/domain/parameters.json` and `src/infra/prompts/templates` (section 2) | owner decision |
| `main.py:1-4`, `infra/ollama_client.py:3-17`, `infra/prompts.py:2`, `shared/decorators.py:5` | docstrings cite deleted ARCHITECTURE.md and legacy packages | trivial |
| `services/parsing/text_loader.py:88` | reads only main + `/Relationships`, not `/Synopsis` (extract_v3 reads all three) | design difference |
| `services/params/step.py` | flags/ordinals step, a feature the owner abandoned | dead per course |

### experiments/jiro_flags_local
| file:line | issue | class |
|---|---|---|
| `run.py:22` | `DUMP = Path("/home/Di/Загрузки/…")`, hardcoded absolute path | obvious |
| `run.py:18` | `sys.path` hack into `src/` for extract_v3 | obvious |
| `run.py:123` | f-string with nested `'\W+'` quotes, needs Python ≥3.12 | note |
| `run.py:106` vs `revalidate.py:214`, `verify_quotes.py:250` | run.py writes `results/*_p1.json` (list; keys `answer_raw`, `answer`, …). revalidate and verify_quotes read and **overwrite** `result.json` (dict; keys `model_said`, `answer`). **The aggregator that builds result.json is missing.** | BROKEN pipeline step |
| `revalidate.py:223` | hardcoded "of 320" (5×64) | trivial |
| `kappa.py:160` | needs p1..p3; only p1 is committed, so every character prints "(incomplete)" | dead |
| `flags.yaml` vs `flags.orig.yaml` | 6 edited `look_for`/`not_this` lines. results/*.json, result.json and flags_result.json are committed outputs (~5.8k lines). | junk/data |

### legacy / root
| file:line | issue | class |
|---|---|---|
| `docker-compose.yaml:8,48,79` | Postgres password `6713` hardcoded in plaintext (3×) | secret, obvious (move to .env) |
| `docker-compose.yaml:22` | `NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-yuzuki_graph}`, a default password committed | secret-ish, obvious |
| `.dockerignore` | contains only `.env`. `.gitignore:66` ignores `.dockerignore` while it is tracked. | obvious |
| README.md:8,20-21,42 | dead image link and dead doc links; describes the legacy pipeline only | obvious (rewrite) |
| `src/infra/ai_clients/cerebras_client.py`, `x_client.py` | imported nowhere | dead code, mention only |
| `src/infra/ai_clients/cerebras_client.py:2`, `src/infra/settings/config.py:43` | cite the deleted `src/experiments/compare_models.py` | trivial |
| `src/repository/scripts/migrate_character_images_to_db.py:7-9` | "Run from src/" contradicts `python -m src.repository…` (that needs the repo root) | trivial |
| docker-compose `volumes: static, media` (lines 112-113) | declared, not used | dead |
| `src/services/collection/cast/steps/models/lbpcascade_animeface.xml` | 6.7k-line binary-ish model (vendored) | fine/legacy |
| history | no API keys found in `git log -p` (AIza/xai-/csk- scan); `.env` never committed | ok |

## 4. Test status

Env: Python 3.13.18; scratchpad venv with pytest 9.2, pydantic, jinja2, mwparserfromhell 0.7.2, httpx 0.28, networkx, pyvis, numpy, pyyaml.

```
$ python -m pytest -q tests/
ERROR tests/yuzuki_local - ModuleNotFoundError: No module named 'yuzuki_local'
  (tests/yuzuki_local/conftest.py:9 `from yuzuki_local.entities.results import CallMetrics, ChatResult`)
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.50s

$ python -m pytest -q tests/ --ignore=tests/yuzuki_local     -> 36 passed in 1.47s
$ python -m pytest -q tests/proto_wiki                        -> 36 passed
```
- The whole suite fails at **collection** because the conftest of tests/yuzuki_local imports a module that does not exist (verified: no `src/yuzuki_local` in the tree or any commit; 90e5839 says it was dropped; the tests were added later, in 79cab25).
- Salvage: `tests/yuzuki_local/test_ollama_client.py`, with its import changed to `extract_v3.external.ollama`, **passes 5/5** (run on a scratch copy). The other 6 files test gone classes (ContextBuilder, FlagSet, TraitAggregator, QuoteVerifier, AnchorMatcher, RelationExtractor/Classifier, OccupationWorker, GroupTyper, OrdinalRater, PromptRenderer).
- extract_v3 has **zero tests**. Its modules import cleanly, except `neo4j_writer` and `run_jiro`, which need the `neo4j` package. `Settings.load()` works. The rendered parse prompt is about 7.4k chars and the rewrite prompt about 4.9k (pass-1 `prompt_eval_count` is about 1531 tokens, fits num_ctx 4096).
- No pytest.ini or pyproject; both conftests use `sys.path.insert(src)`.

## 5. What the pipelines do

### extract_v3 (current)
1. `text_prep.load_sentences(dump_path, pages, drop_sections)`. `DumpReader` streams the XML. For pages `["Kyoka Jiro", "/Relationships", "/Synopsis"]` in fixed order, `WikiTextCleaner(min_paragraph_words=4).sections()` drops infobox/ref/table/gallery/File links, keeps Nihongo/Ruby first param, and skips reference-like sections plus their subsections. Then drop_sections, then a regex sentence split (protecting acronyms like U.A. and "No. 30"). Output: `Sentence(id, page, section, text)`, with ids sequential across pages.
2. **Pass 1, rewrite** (`rewriter.Rewriter.rewrite`): one Ollama call per sentence. The prompt (`prompts/rewrite_prompt.j2`) has 15 rules (resolve pronouns to the roster's canonical names, active voice with agentless subjects becoming "people", present simple, split enumerations, purpose clauses to "wants to", appositions, relative clauses, reciprocals, group actions, keep frequency/degree/certainty/"used to"; conditionals become `["HYPOTHETICAL"]`), invented-character few-shots, and the roster. The target is marked `<<<…>>>` with ±3 neighbour sentences from the same page+section. Schema `RewriteReply{simple_sentences: list[str]}`. Cached in `.pass1_<run>.json`.
3. **Pass 2, parse** (`parser_llm.LlmParser.parse`): one call per simple sentence, giving exactly one `ParseReply{kind: edge|property, subject, subject_type: character|group|people, predicate (1 word, generalised), predicate_raw, property (1 word), target, target_type (free str), via, description, modality: none|want|can|must, negated, mutual, frequency, degree, certainty: fact|implied|rumored, former}`. Checkpoint `.checkpoint_<run>.json`.
4. **Neo4j** (`neo4j_schema.ensure_constraints`, `neo4j_writer.write_roster`, `FactWriter.write_one`):
   - Nodes: `:Universe{name}`, `:Character{name, aliases}` and `:Group{name, aliases}` each with `-[:IN_UNIVERSE]->`, `:People{universe}`, `:Concept{name, embedding}`.
   - Edges: `(s)-[:EDGE{edge_key=sha1(subj|pred|tgt|simple_id|variant|run_id), predicate, predicate_raw, predicate_embedding, via, description, description_embedding, modality, negated, mutual, frequency, degree, certainty, former, simple_sentence_id, source_sentence_id, section, variant, run_id, model, prompt_version, created_at, source_sentence}]->(o)` and `(s)-[:HAS_PROPERTY{…}]->(:Concept{name=property})`.
   - Embeddings: fastembed `BAAI/bge-small-en-v1.5` (passage mode).
5. `report.build_report` reads facts back from Neo4j by run_id and writes `extract_v3/REPORT.md`: timing, source-to-simple table, simple-to-fact table, predicate_raw to predicate counts, 20 random chains, a Cypher snippet.
- Roster: hand-written in config.yaml (28 MHA characters, 3 groups) and injected into both prompts.

### proto_wiki (older prototype)
`cli.main` -> `main.run(input_path, character, params_path, out_dir, llm, fresh)`:
1. `text_loader.load_document` reads main + `/Relationships` from the dump (or wikitext/plain file) and returns `Document(paragraphs, aliases)`. The alias dict comes from `[[Target|text]]` link pairs.
2. `coref.run_coref`: one call per paragraph. System `system_prompt_coref.j2` says to replace pronouns with full names and change nothing else. Schema `CorefOutput{text}`. The output is rejected if its length ratio falls outside 0.7-1.6.
3. `triples.run_triples`: one call per paragraph, with numbered sentences. Closed relation vocab grouped by object type (Character: family_of…fears; Organization: member_of/leader_of/opposes; Item: owns/uses/created; Concept: believes_in/pursues/rejects; Activity: enjoys/skilled_in). Schema `TripleLLM{sentence_id, subject, subject_type, relation (Literal), object, object_type, item_class}`. Drops bad sentence_id, empty names, type mismatches and duplicates.
4. `graph.build_graph`: normalises names via aliases and the character's name parts, merges duplicates with counts, writes `graph.json` and an offline pyvis `graph.html`.
5. `params.run_params`: one call per param from `parameters.json` (51 flags as T1/T2/T3/unknown, 6 ordinals). Schema is `evidence, reason, tier`, in that order. A verbatim quote check (≥10 chars, normalised) else `evidence_not_found`.
6. `report.build_report` writes `report.md`. `StepCache` caches each step as JSON in out_dir, keyed by a digest of model + template source + inputs.

### Reusable pieces for a new harness (all in `src/extract_v3/external/`, no repo deps)
```python
# dump_reader.py   (stdlib only)
@dataclass(frozen=True) class DumpPage: title: str; ns: int; text: str
class DumpReader:
    def __init__(self, path: Path)
    def pages(self) -> Iterator[DumpPage]        # streaming iterparse, last revision, el.clear()

# wikitext_cleaner.py   (mwparserfromhell)
@dataclass(frozen=True) class WikiSection: name: str; paragraphs: tuple[str, ...]; chars -> int (property)
SKIP_SECTIONS = ("references","navigation","site navigation","gallery","image gallery","external links",
                 "see also","notes","appearances","voice actors","merchandise","video game appearances")
class WikiTextCleaner:
    def __init__(self, min_paragraph_words: int = 4)
    def sections(self, text: str, intro_name: str = "Introduction") -> list[WikiSection]
    def clean_line(self, line: str) -> str

# ollama.py   (httpx, pydantic)
@dataclass(frozen=True) class CallMetrics: prompt_eval_count, prompt_eval_ms, eval_count, eval_ms, total_ms, load_ms, attempts
@dataclass(frozen=True) class ChatResult(Generic[T]): parsed: T; raw: str; metrics: CallMetrics
class LLMError(Exception): raw: str; metrics: CallMetrics
class PromptTooLong(LLMError)                     # not retried
class OllamaClient:
    def __init__(self, model: str, num_ctx: int, num_predict: int, keep_alive: str = "30m",
                 timeout_s: float = 900.0, retries: int = 2, host: str | None = None,
                 sleep=time.sleep, transport=None)  # host defaults to $OLLAMA_HOST or 127.0.0.1:11434; transport injectable for tests
    def chat(self, prompt: str, response_model: type[T], temperature: float = 0.0,
             num_predict: int | None = None) -> ChatResult[T]   # single user message, format=JSON schema, think=False (auto-dropped on 400)
    def load(self) -> bool                         # True if fully in VRAM
    def close(self) -> None

# embedder.py   (numpy, lazy fastembed)
class Embedder:
    def __init__(self, model_name: str)
    def embed(self, texts: list[str], is_query: bool = False) -> np.ndarray   # L2-normalised; BGE query instruction / e5 prefixes

# neo4j_client.py   (neo4j driver)
class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str)
    def session(self)  # contextmanager
    def close(self) -> None
```
Also reusable:
- `extract_v3/text_prep.py`: `load_sentences(dump_path, page_titles: tuple[str,...], drop_sections: tuple[str,...]) -> list[Sentence]`, plus `_split()` with acronym protection.
- `extract_v3/prompt_renderer.py`: `PromptRenderer.rewrite(...)`, `.parse(...)`, `.template_hash(name) -> sha1[:12]`.
- `extract_v3/resolve.py`: `build_lookup(characters, groups) -> dict`, `canonicalize(name, lookup) -> str`.
- `extract_v3/settings.py`: `Settings.load(path=None)` (yaml + `NEO4J_*` env/.env).
- From proto_wiki:
  - `services/parsing/text_loader.py` `_link_pairs` / `_build_alias_dict`: wiki-link alias harvesting, which extract_v3 lacks.
  - `services/triples/step.py` `split_sentences` (abbreviation-aware).
  - `services/params/step.py` `evidence_found` (quote verification).
  - `repository/step_cache.py` `StepCache(out_dir).read(filename, key, fresh)` / `.write(...)` and `digest(*parts)`: a better cache keying than extract_v3's.
- From jiro_flags_local: `run.quote_ok(quote, ctx_norm, ctx_tri, threshold=0.85)` (trigram-tolerant quote check).

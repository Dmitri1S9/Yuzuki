# Architecture

All code lives under `src/`, split by architectural layer. Root holds only
service files that can't live anywhere else: Docker/compose, `.env`, shell
runners, docs, and `db`-unrelated auxiliary tooling (`kappa_analysis.R`).

```
src/
  domain/       pure data model — Character, Universe, Group, Relation,
                GroupRelation, and the single-source parameter registry
                (parameters.py + parameters.json — both the 6 ordinals and
                the 51 flags, one file). No I/O.
  repository/   DB access — one class per aggregate (UniverseRepository,
                CharacterRepository, GroupRepository, RelationRepository),
                always returns domain objects, never raw dicts/tuples.
  services/     business logic, one runnable pipeline stage = one
                subfolder = one main.py:
                  collection/cast/       stage 1 — roster + groups
                  collection/relations/  stage 3 — relations + group_relations
                  collection/features/   stage 2 — ordinal ranks + flags
                  consensus/             library only (no main.py) — the
                                          maximin-kappa weak-order ranker,
                                          used only by collection/features
                  graph/                 stage 4 — pyvis rendering, run
                                          manually, not part of run_pipeline.sh
  infra/        external systems: ai_clients (Gemini/X + schemas), prompts
                (Jinja loader + templates), settings (config/logging/redis),
                dcs_client.py (pushes drafts to DCS — see below), exceptions.
  shared/       cross-cutting utilities used across layers: naming.py
                (slugify/arg parsing), decorators.py (@announce/@report).
  api/          FastAPI app — the ONLY place cast/relations output actually
                lands in Postgres now. See "DCS" below.
```

## The "one `main.py` per level" rule

Every **runnable** package (an independent pipeline stage) has a `main.py`
containing *only* the `main()` ladder — a flat, top-to-bottom sequence of
named calls, each one a step defined in a sibling file in the same package.
No step logic, no loops, no inline computation lives in `main.py` itself;
only imports, the unavoidable env-var bootstrap that must run before the
first import that touches `Settings()`, the `main()` ladder, and the
`if __name__ == "__main__":` guard.

Library packages (`domain/`, `repository/`, `infra/`, `services/consensus/`)
are never run standalone, so they have no `main.py` — just their own files
plus an `__init__.py` exporting the public API.

## Decorators — where the cross-cutting stuff goes

Two flavors, pick whichever fits the file:

- **Module-level** (`src/shared/decorators.py`'s `@announce`/`@report`,
  used throughout `services/collection/*`): stack closest-to-function first.
  The one right above `def` matters most (it can shape what's returned); the
  ones further up only narrate. A step function's own body is never
  responsible for logging that it started or summarizing its own result —
  that's the decorator's job.
- **Class-based** (private, name-mangled decorator *methods* defined inside
  the class, e.g. `GeminiClient.__cached`, `src/repository/connection.py`'s
  `@transactional`/`@read_only`): the connect/commit/rollback/close
  boilerplate that used to be copy-pasted into every single `db/service.py`
  function now lives in exactly those two decorators — a repository method
  body is never anything but its own SQL. Same idea for `GeminiClient`/
  `XClient`: `__cached` is the only thing touching Redis; `_request` itself
  only ever builds the request and calls the model.

## Domain objects: closed, not sealed

`Character`, `Universe`, `Group`, `Relation`, `GroupRelation` are built once
from repository query results and are read-only afterward — private
`_`-prefixed state, public getters, no setters. They're convenience
pointers into the database, not a modeling layer with business logic of
their own.

`Character.get_<param>()` methods (`get_combat_potential()`, `get_cruel()`,
`get_gender()`, ...) aren't hand-written: `src/domain/character.py`
generates one per name in `src/domain/parameters.py`'s `PROFILE_PARAMS`/
`ORDINAL_PARAMS`/`FLAG_PARAMS` — all three loaded from
`src/domain/parameters.json`, the single file holding every one of a
character's 61 parameters (`"profile"` and `"ordinals"` categories sit
alongside the 7 flag categories in the same JSON — nothing about what a
character can be asked for is split across two sources). Add, rename, or
redefine a parameter there and every consumer — the getters, `__getitem__`,
`help()`, the repository's filter validation, the features collection stage
— follows without being edited by hand.

Every domain class also has:
- **`help()`** (classmethod) — prints and returns the field/parameter names
  available on that class. For `Character` this is read live off
  `parameters.json`, so it never drifts from the actual getter list.
- **`__eq__`/`__hash__`** — identity by the natural key (`Character`:
  universe + name; `Group`: type + name; `Relation`: type + source_level +
  endpoints; `GroupRelation`: kind + the unordered group pair; `Universe`:
  id) — two objects pointing at the same row compare equal and hash the
  same, so they work in sets/dicts.
- **`__str__`**/**`__repr__`** — a short human label vs. an unambiguous one.
- **`Character.__getitem__`** — `character["cruel"]` as a dynamic-name
  alternative to `get_cruel()`, dispatching through the same three
  registries (only on `Character`, since it's the one class with a large,
  JSON-driven parameter set — `Group`/`Relation`/`Universe`'s few fields are
  structural, not a swappable list, so plain getters already cover them).

## DCS — human review before anything is final

[DCS (Droid Command Station)](../DCS) is a separate sibling project (own
repo, own `docker-compose.yaml`) that puts a human review/approval gate in
front of stage 1 (roster+groups) and stage 3 (relations, as an editable
graph). It talks to Yuzuki only over HTTP — never touches Postgres
directly.

**The flow changed because of this:** `cast/persistence.py` and
`relations/persistence.py` no longer write groups/relations to Postgres
themselves. Instead they register the universe (idempotent, just enough to
have a real `universe_id`) and push a draft to DCS via
`src/infra/dcs_client.py`. A human reviews/edits it in DCS's UI and clicks
Approve, which calls back into `src/api/routes/confirm.py` — that's the
only place `GroupRepository`/`RelationRepository` actually get written for
that data now. `src/api/main.py` needs to be running as a persistent server
(`docker compose up -d analyse_service`, not just the one-off `docker
compose run` pipeline-stage invocations) for this callback to reach it.

`features/persistence.py` pushes stage 2's per-parameter kappa quality to
DCS too, but push-only — no edit loop, no confirm callback. The numbers
(`min_kappa`, `kappa_raw_min`, ...) are already computed by
`consensus_rank()`; DCS just renders them color-coded.

**Invariant: a low-reliability (DROP) verdict is never a reason to remove a
parameter for the whole universe.** It's diagnostic only. Unreliable
agreement is always handled per character — `consensus_rank()` nulls that
one character's value when its passes disagree (see its own docstring) —
never by dropping the parameter for everyone. `KappaReview.tsx` in DCS has
no "drop parameter" action for exactly this reason; if this view ever grows
editing, this invariant still applies.

`run_pipeline.sh` still runs stage 1 → 3 → 2 straight through without
waiting — the JSON handoff files between stages are unaffected by any of
this (stage 2 still reads stage 1's roster from
`run/stage1_cast_{slug}.json`, same as always). What's decoupled is
specifically *when confirmed data lands in Postgres* — that now happens
whenever the human gets to DCS, independent of the pipeline script's own
pace.

`GroupRepository.save_groups`/`RelationRepository.save_relations` gained a
`replace=True` path for this (delete-then-insert instead of a bare
`INSERT`) — a re-approval replaces the previously confirmed set instead of
piling duplicate rows on top of it, which also incidentally fixes the
row-duplication a plain pipeline rerun caused before (`GroupRepository`/
`RelationRepository` are still called without `replace=True` from
`group_relations`' direct-write path, since that one isn't part of the DCS
review flow — see Known gaps).

## Known gaps (not fixed by the reorg, not silently pretended away)

- **stage2 (ordinal/flag) results are not persisted to the database.**
  `Character.get_flag()`/`get_ordinal()` are wired up correctly and will
  work the moment this is closed, but today they return `None` for every
  character — stage2 only ever wrote `stage2_features_{slug}.json` (and
  still does). Needs its own schema/persistence design pass.
- **Profile fields (`body_age`/`soul_age`/`gender`/`species`) are read from
  real `characters` columns, but nothing in the live pipeline writes them.**
  `BaseAIClient.profile()` exists but no stage script calls it — profile
  collection was only ever wired through the deleted Celery path. A handful
  of characters carry values from an earlier manual test; everyone else
  reads back `None`.
- **`low_info` is derived, not stored.** It's computed fresh by stage 3 into
  `relations_merged_{slug}.json` each run; there's no `characters.low_info`
  column, so a `Character` loaded from the repository doesn't carry it.
- **`group_relations` (allied/rival) reliability** is a known open issue,
  being handled by hand outside this codebase.

## Inter-stage JSON files vs. the database

Each pipeline stage runs as its own `docker compose run` process — there's
no shared memory between them. `stage1_cast_{slug}.json`,
`relations_passes_{slug}.json`, and `relations_merged_{slug}.json` are this
run's handoff mechanism between stages (stage 3 reads stage 1's file, stage
2 reads both, stage 4 reads both) and get overwritten on every run. All of
them — plus the pass CSVs, `kappa_verdicts_{slug}.csv`, and the rendered
graph HTML files — live under `run/` (gitignored, via `src/shared/paths.py`)
instead of scattered loose across the project root. The database is the
durable, cross-run record — roster, groups, relations, and group_relations
are written there by stage 1 and stage 3 directly, via `src/repository`.

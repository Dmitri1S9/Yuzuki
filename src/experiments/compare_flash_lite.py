"""One-off: does gemini-3.1-flash-lite hold up for groups/relations/alias
the way it already does for flags/profile? Those tasks are already
maximally simplified (single pass, no per-item nuance to hold across a
BOUNDARY/ANTI clause) — the user's hypothesis is that they lean on the
model's anime-domain KNOWLEDGE more than on complex reasoning, so a cheaper
tier might lose little. This tests that empirically instead of guessing.

Zero re-spend on the flash side: reuses MHA Sports Festival Arc's already-
collected flash output (stage1_cast_..., relations_passes_...) as the
reference. Only flash-lite makes new calls, 1 pass each, matching what a
single flash pass produced — not the full multi-pass pipeline.

IMPORTANT: GeminiClient's own cache key is NOT namespaced by model (it's
built purely from rendered prompt text — see gemini_client.py). Reusing
GeminiClient's cache un-namespaced here would silently return production
flash's cached answer instead of ever calling flash-lite, since a
lite-vs-flash swap doesn't change the rendered prompt at all. The client
below gets its own prefixed cache, same fix already applied to
CerebrasClient/XClient this session.

Not part of the real pipeline — throwaway diagnostic, run by hand:
    python -m src.experiments.compare_flash_lite
"""
import functools
import json
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from src.infra.ai_clients.base_client import CACHE_TTL, BaseAIClient, thinking_for
from src.infra.settings.config import Settings
from src.infra.settings.redis_client import redis_cache
from src.services.collection.cast.steps.groups import overlap
from src.services.collection.cast.steps.name_matching import name_key
from src.services.collection.relations.steps.character_relations import canon_pair, pairs_from_result

T = TypeVar("T", bound=BaseModel)

UNIVERSE_NAME = "My Hero Academia"
ARC = "Sports Festival Arc"
LOCATION = None
SLUG = "my_hero_academia_sports_festival_arc"
RELATION_TYPES = ("for", "against", "want", "with")


def make_lite_client(thinking_budget: int) -> type[BaseAIClient]:
    class GeminiLiteClient(BaseAIClient):
        model_group = model_relation = model_alias = "gemini-3.1-flash-lite"
        thinking_group = thinking_relation = thinking_alias = thinking_budget
        temperature_group = temperature_alias = 0.0
        temperature_relation = 0.0  # deterministic single pass — isolate the
                                      # model-quality question, not add
                                      # temperature-driven variance on top

        _settings = Settings()

        def __init__(self) -> None:
            self._client = genai.Client(api_key=self._settings.api_key_gimini)

        def __cached(fn):
            @functools.wraps(fn)
            def wrapper(self, response_model, system_prompt, user_prompt, cache_key,
                        model, thinking=0, temperature=0.1):
                namespaced_key = f"lite-experiment:{model}:{cache_key}"
                cached = redis_cache.get(namespaced_key)
                if cached:
                    return response_model.model_validate_json(cached)
                result = fn(self, response_model, system_prompt, user_prompt, cache_key,
                            model, thinking, temperature)
                redis_cache.set(namespaced_key, result.model_dump_json(), ex=CACHE_TTL)
                return result
            return wrapper

        @__cached
        def _request(self, response_model, system_prompt, user_prompt, cache_key,
                     model, thinking=0, temperature=0.1):
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=response_model,
                max_output_tokens=65536,
                temperature=temperature,
                thinking_config=types.ThinkingConfig(thinking_budget=thinking),
            )
            response = self._client.models.generate_content(model=model, contents=user_prompt, config=config)
            return response_model.model_validate_json(response.text)

    return GeminiLiteClient


def load_json(name: str) -> dict:
    with open(f"run/{name}_{SLUG}.json", encoding="utf-8") as f:
        return json.load(f)


def compare_groups(client) -> None:
    print("\n=== GROUPS (medium) ===")
    stage1 = load_json("stage1_cast")
    flash_groups = stage1["groups"]["medium"]
    result = client.group("medium", UNIVERSE_NAME, ARC, pass_number=1, location=LOCATION)
    lite_groups = result["groups"]
    print(f"flash groups: {len(flash_groups)}  lite groups: {len(lite_groups)}")

    matched_flash = set()
    for lg in lite_groups:
        lg_members = {name_key(m) for m in lg["members"]}
        best_name, best_score = None, 0.0
        for fg in flash_groups:
            fg_members = {name_key(m) for m in fg["members"]}
            score = overlap(lg_members, fg_members)
            if score > best_score:
                best_name, best_score = fg["name"], score
        if best_score >= 0.3:
            matched_flash.add(best_name)
        print(f"  lite {lg['name']!r:35s} (n={len(lg['members']):2d}) -> best flash match "
              f"{best_name!r} overlap={best_score:.2f}")

    missed = [fg["name"] for fg in flash_groups if fg["name"] not in matched_flash]
    print(f"flash groups with no decent lite match (overlap<0.3): {missed}")


def compare_relations(client) -> None:
    print("\n=== RELATIONS (general_pool round 1, pass 1) ===")
    passes = load_json("relations_passes")
    round1 = passes["general_pool"][0]
    roster = round1["candidates"]
    print(f"roster n={len(roster)}")

    for rt in RELATION_TYPES:
        flash_pass1 = round1["results"][rt]["1"]
        flash_pairs = {canon_pair(rt, p) for p in pairs_from_result(rt, flash_pass1)}

        result = client.relations(rt, roster, UNIVERSE_NAME, ARC, pass_number=1, temperature=0.0)
        lite_pairs = {canon_pair(rt, p) for p in pairs_from_result(rt, result)}

        inter = flash_pairs & lite_pairs
        precision = len(inter) / len(lite_pairs) if lite_pairs else float("nan")
        recall = len(inter) / len(flash_pairs) if flash_pairs else float("nan")
        f1 = (2 * precision * recall / (precision + recall)
              if precision + recall > 0 and not (precision != precision) else float("nan"))
        print(f"  {rt:8s} flash={len(flash_pairs):3d} lite={len(lite_pairs):3d} "
              f"overlap={len(inter):3d} precision={precision:.2f} recall={recall:.2f} f1={f1:.2f}")


def compare_aliases(client) -> None:
    print("\n=== ALIASES ===")
    stage1 = load_json("stage1_cast")
    roster_names = [r["name"] for r in stage1["roster"]]
    flash_pairs = set()
    for r in stage1["roster"]:
        for alias in r.get("aliases", []):
            flash_pairs.add(tuple(sorted((name_key(r["name"]), name_key(alias)))))
    print(f"roster n={len(roster_names)}  flash confirmed alias pairs: {len(flash_pairs)}")

    result = client.alias_names(roster_names, UNIVERSE_NAME, ARC, pass_number=1)
    canon_keys = {name_key(n) for n in roster_names}
    lite_pairs = set()
    for entry in result.get("entries", []):
        other = entry.get("other_name")
        if not other:
            continue
        key_a, key_b = name_key(entry["name"]), name_key(other)
        if key_a == key_b or key_b not in canon_keys:
            continue
        lite_pairs.add(tuple(sorted((key_a, key_b))))

    inter = flash_pairs & lite_pairs
    print(f"lite proposed pairs (after filtering to known names): {len(lite_pairs)}")
    print(f"overlap with flash's confirmed pairs: {len(inter)}/{len(flash_pairs)}")
    if flash_pairs - inter:
        print(f"flash pairs lite missed: {flash_pairs - inter}")
    if lite_pairs - inter:
        print(f"lite pairs flash never confirmed (may be noise, or flash under-collected): {lite_pairs - inter}")


def main():
    # A representative size for the general_pool roster (~61) — same budget
    # used for every call type here, not re-derived per call, since this is
    # a fixed-size diagnostic run, not the adaptive production path.
    budget = thinking_for([""] * 61)
    print(f"thinking_budget for this run: {budget}")
    client_cls = make_lite_client(budget)
    client = client_cls()

    compare_groups(client)
    compare_relations(client)
    compare_aliases(client)


if __name__ == "__main__":
    main()

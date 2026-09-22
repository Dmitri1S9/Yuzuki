"""One-off: how much do cheaper models lose against Gemini on a small
sample of parameters, using MHA Sports Festival Arc's real, already-
collected roster? Compares two hosts serving the same gpt-oss-120b model
(Cerebras, Groq) — same model, different serving, a cheap cross-check of
whether any quality gap is about the model or about a specific host.

Zero new Gemini spend — the comparison target is the Gemini consensus
result already sitting in run/stage2_features_{slug}.json from today's
real run, not a fresh Gemini call. Each alternative client makes one pass
per sampled parameter, not the full 3-pass pipeline, to stay well inside
free-tier quotas.

Not part of the real pipeline, not written in the ladder+decorator style —
this is a throwaway diagnostic, run by hand:
    python -m src.experiments.compare_models
"""
import functools
import json
import os
import re
from typing import TypeVar

os.environ.setdefault("REDIS_URL_CACHE", "redis://localhost:6379/1")
os.environ.setdefault("REDIS_URL_CELERY", "redis://localhost:6379/0")

import numpy as np
from google import genai
from google.genai import types
from pydantic import BaseModel

from src.domain.parameters import ORDINAL_PARAMS
from src.infra.ai_clients.base_client import CACHE_TTL, BaseAIClient
from src.infra.ai_clients.x_client import XClient
from src.infra.settings.config import Settings
from src.infra.settings.redis_client import redis_cache
from src.services.collection.features.steps.collection import compute_score, parse_sorted
from src.services.consensus.metric import cohen_kappa_masked, sign_matrix

T = TypeVar("T", bound=BaseModel)

UNIVERSE_NAME = "My Hero Academia"
ARC = "Sports Festival Arc"
SLUG = "my_hero_academia_sports_festival_arc"

# A small, deliberately mixed sample: some flags with sharp ANTI/BOUNDARY
# clauses (the kind of nuance a weaker model is most likely to miss), one
# broad worldview flag, one ordinal.
SAMPLE_FLAGS = ["cruel", "is_strategist", "is_machiavellian", "goal_power", "has_tragic_past", "is_intimidating"]
SAMPLE_ORDINALS = ["combat_potential"]


def make_grok_client(model_id: str) -> type[XClient]:
    """One xAI subclass per pricier tier to test (4.20, 4.3, 4.6, ...) —
    XClient's cache is already namespaced by model (see x_client.py), so
    each swapped-in model_* can't collide with another tier's cached
    results."""
    attrs = {
        f"model_{field}": model_id
        for field in ("rank", "flag", "profile", "group", "relation", "alias", "group_relations")
    }
    return type(f"Grok_{model_id.replace('.', '_').replace('-', '_')}Client", (XClient,), attrs)


class GeminiCheapClient(BaseAIClient):
    """A cheaper Gemini generation (2.5 Flash-Lite, $0.10/$0.40 per 1M vs.
    the pipeline's current 3.1 Flash-Lite at $0.25/$1.50) — same model
    family as the real pipeline, so the fairest test of "how much does
    stepping down within Gemini itself cost in quality." Own cache
    namespace (by model), independent of GeminiClient's production cache.
    """

    model_rank = model_flag = model_profile = model_group = model_relation \
        = model_alias = model_group_relations = "gemini-2.5-flash-lite"

    thinking_rank = thinking_profile = thinking_group = thinking_relation \
        = thinking_alias = thinking_group_relations = 0  # 2.5-gen doesn't take thinking_level

    _settings = Settings()
    temperature_rank = temperature_flag = temperature_profile = _settings.temperature
    temperature_group = temperature_relation = temperature_alias = 0.4
    temperature_group_relations = 0.0

    def __init__(self) -> None:
        self._client = genai.Client(api_key=self._settings.api_key_gimini)

    def __cached(fn):
        @functools.wraps(fn)
        def wrapper(self, response_model, system_prompt, user_prompt, cache_key,
                    model, thinking=0, temperature=0.1):
            namespaced_key = f"gemini-experiment:{model}:{cache_key}"
            cached = redis_cache.get(namespaced_key)
            if cached:
                return response_model.model_validate_json(cached)
            result = fn(self, response_model, system_prompt, user_prompt, cache_key,
                        model, thinking, temperature)
            redis_cache.set(namespaced_key, result.model_dump_json(), ex=CACHE_TTL)
            return result
        return wrapper

    @__cached
    def _request(self, response_model: type[T], system_prompt: str, user_prompt: str,
                 cache_key: str, model: str, thinking: int | str = 0, temperature: float = 0.1) -> T:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=response_model,
            max_output_tokens=65536,
            temperature=temperature,
        )
        response = self._client.models.generate_content(model=model, contents=user_prompt, config=config)
        return response_model.model_validate_json(response.text)


CANDIDATES: dict[str, type[BaseAIClient]] = {
    # cerebras/gpt-oss-120b (0.171), grok-4-1-fast-reasoning (0.262),
    # grok-4.20-0309-non-reasoning (0.230), grok-4.3 (0.276) already have a
    # confirmed result — not re-run here. grok-4.6 never finished (repeated
    # 90s timeouts even with the fix in place) — impractically slow for
    # batch use, not re-attempted.
    # New: grok-4.7 — priced below gemini-3.8-flash per the user, worth a
    # fresh look.
    "xai/grok-4.7": make_grok_client("grok-4.7"),
    # gemini/gemini-2.5-flash-lite deliberately excluded — Google has
    # retired it for new API keys ("no longer available to new users"),
    # confirmed via a live 404 on this exact key. GeminiCheapClient is kept
    # below in case a genuinely cheaper Gemini tier becomes available later.
}

# Optional [brackets]: the tier calibration text in the rank prompt itself
# shows markers as "[T1] A person who..." and the model sometimes echoes
# that bracketed style into the output instead of the schema's bare "T1" —
# same fix applied to the real pipeline (features/collection.py) after
# catching it live on Gemini's own intellect collection.
RANK_RE = re.compile(r"^\[?T\d+\]?$")


def load_gemini_reference() -> dict:
    with open(f"run/stage2_features_{SLUG}.json", encoding="utf-8") as f:
        return json.load(f)


def load_roster(gemini_ref: dict) -> tuple[list[str], set[str]]:
    roster = [r["name"] for r in gemini_ref["roster"]]
    low_info = {r["name"] for r in gemini_ref["roster"] if r["low_info"]}
    return roster, low_info


def compare_one(client: BaseAIClient, param: str, is_ordinal: bool,
                 roster: list[str], gemini_features: dict) -> float | None:
    if is_ordinal:
        result = client.rank(ORDINAL_PARAMS[param], roster, UNIVERSE_NAME, ARC)
    else:
        result = client.flag(param, roster, UNIVERSE_NAME, ARC)

    positions, segments = parse_sorted(result["sorted"], RANK_RE)
    candidate_scores = {name: compute_score(positions.get(name), segments) for name in roster}

    eligible = [
        n for n in roster
        if gemini_features.get(n) and gemini_features[n].get(param) is not None
        and candidate_scores.get(n) is not None
    ]
    if len(eligible) < 5:
        print(f"    {param:26s} not enough overlap to compare (n={len(eligible)})")
        return None

    # Same order-agreement metric consensus_rank/kappa_analysis.R already
    # use — robust to the two sides being on different absolute scales
    # (Gemini's block_index vs. the candidate's raw tier*10+within), since
    # it only compares pairwise sign of difference, not the raw values.
    gemini_arr = np.array([gemini_features[n][param]["block_index"] for n in eligible], dtype=float)
    candidate_arr = np.array([candidate_scores[n] for n in eligible], dtype=float)
    g_codes, g_valid = sign_matrix(gemini_arr)
    c_codes, c_valid = sign_matrix(candidate_arr)
    kappa = cohen_kappa_masked(g_codes, c_codes, g_valid & c_valid)
    print(f"    {param:26s} n={len(eligible):3d}  kappa(gemini vs candidate)={kappa:.3f}")
    return kappa


def run_candidate(label: str, client_cls: type[BaseAIClient], roster: list[str], gemini_features: dict) -> None:
    print(f"\n=== {label} ===")
    try:
        client = client_cls()
    except Exception as e:
        print(f"    could not start client: {e}")
        return

    kappas = []
    for param in SAMPLE_ORDINALS:
        try:
            k = compare_one(client, param, True, roster, gemini_features)
        except Exception as e:
            print(f"    {param:26s} FAILED: {e}")
            k = None
        if k is not None:
            kappas.append(k)
    for param in SAMPLE_FLAGS:
        try:
            k = compare_one(client, param, False, roster, gemini_features)
        except Exception as e:
            print(f"    {param:26s} FAILED: {e}")
            k = None
        if k is not None:
            kappas.append(k)

    if kappas:
        print(f"    average kappa: {sum(kappas) / len(kappas):.3f}")
    else:
        print("    no comparable parameters — nothing to average")


def main():
    gemini_ref = load_gemini_reference()
    gemini_features = {name: gemini_ref["features"][name] for name in gemini_ref["features"]}
    roster_full, low_info = load_roster(gemini_ref)
    roster = [n for n in roster_full if n not in low_info]
    print(f"comparing on {len(roster)} characters (low_info excluded, same as the real Gemini run)")

    for label, client_cls in CANDIDATES.items():
        run_candidate(label, client_cls, roster, gemini_features)


if __name__ == "__main__":
    main()

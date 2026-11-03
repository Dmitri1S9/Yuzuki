from abc import ABC, abstractmethod
from typing import TypeVar
from pydantic import BaseModel
from src.infra.prompts.loader import get_prompt
from src.infra.ai_clients.schemas.ranker_schema import RankingResponse
from src.infra.ai_clients.schemas.flag_schema import FlagRankResponse
from src.infra.ai_clients.schemas.profiler_schema import ProfileResponse
from src.infra.ai_clients.schemas.groups_schema import GroupsResponse
from src.infra.ai_clients.schemas.relations_schema import SymmetricResponse, DirectedResponse
from src.infra.ai_clients.schemas.alias_schema import AliasNamesResponse
from src.infra.ai_clients.schemas.group_relations_schema import GroupPairsResponse
from src.infra.exceptions import falseRelationTypeException
from src.domain.parameters import FLAG_PARAMS
import json
import hashlib

T = TypeVar("T", bound=BaseModel)

CACHE_TTL = 60 * 60 * 24 * 14
# relation_type -> "directed" (source/target) or "symmetric" (members)
RELATION_TYPES = {"for": "directed", "against": "symmetric", "want": "directed", "with": "symmetric"}
# group_relation_kind -> the {{ relation_desc }} text substituted into the prompt
GROUP_RELATION_DESC = {
    "allied": "the groups act together toward a shared goal",
    "rival": "the groups act against each other",
}


def hash_args(*args) -> str:
    return hashlib.sha256(
        json.dumps(args, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def prompt_cache_key(prefix: str, system_prompt: str, user_prompt: str, pass_number: int | None = None) -> str:
    """Cache key derived from the exact rendered prompt text, not just the
    semantic call args — so any prompt/template edit invalidates the cache
    on its own, with no manual flush needed. pass_number is included
    separately since it never appears in the rendered text itself."""
    digest = hashlib.sha256(
        json.dumps([system_prompt, user_prompt, pass_number], ensure_ascii=False).encode()
    ).hexdigest()
    return f"{prefix}:{digest}"


def thinking_for(characters: list[str]) -> int:
    # Thinking tokens bill as output tokens, and flag() calls this once per
    # flag (51 flags x 1 pass per universe) — for a large roster this was
    # the single biggest line item in the whole pipeline (e.g. ~9k tokens x
    # 51 calls for a 109-character universe, more than the rest of the
    # universe's cost combined). Halved both the per-character scaling and
    # the ceiling (2026-09-23, cost cut) — a plain list-membership judgment
    # doesn't need as much budget as a multi-way ranking does.
    return min(1024 + 32 * len(characters), 8192)


def get_flag_def(name: str) -> dict:
    # FLAG_PARAMS is the single source of truth (src/domain/parameters.py) —
    # flattened once from parameters.json, not re-read here.
    if name not in FLAG_PARAMS:
        raise ValueError(f"Flag '{name}' not found in parameters.json")
    return FLAG_PARAMS[name]


class BaseAIClient(ABC):

    # None = scale numerically by roster size (thinking_for) — what the
    # non-Gemini clients still rely on; GeminiClient overrides with a level.
    thinking_flag: int | str | None = None

    @abstractmethod
    def _request(
        self,
        response_model: type[T],
        system_prompt: str,
        user_prompt: str,
        cache_key: str,
        model: str,
        thinking: int | str = 0,
        temperature: float = 0.1,
        force_refresh: bool = False,
    ) -> T:
        # thinking: int = numeric thinking_budget (older models), str ("low"/
        # "medium"/"high") = thinking_level (Gemini 3.6+ Flash). The two are
        # mutually exclusive on the API side — never pass both in one call.
        ...

    def rank(
        self,
        prompt: str,
        characters: list[str],
        universe: str,
        arc: str | None = None,
        context: str | None = None,
        pass_number: int | None = None,
        force_refresh: bool = False,
    ) -> dict:
        system_prompt = get_prompt("system_prompt_ranker", time_period=arc or "entire series")
        user_prompt = get_prompt(prompt, universe=universe, characters=characters, arc=arc, context=context)
        result = self._request(
            response_model=RankingResponse,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cache_key=prompt_cache_key("rank", system_prompt, user_prompt, pass_number),
            model=self.model_rank,
            thinking=self.thinking_rank,
            temperature=self.temperature_rank,
            force_refresh=force_refresh,
        )
        return result.model_dump()

    def flag(self, flag_name: str, characters: list[str],
                universe: str, arc: str | None = None, context: str | None = None,
                pass_number: int | None = None, force_refresh: bool = False) -> dict:
        # Back to a sorted-with-tiers placement (T1/T2/T3), not plain list
        # membership — 2026-09-23, user's call after live review: a flat
        # "who has it" list gave no way to tell a borderline match from a
        # strong one, so characters barely worth including (~1% of a flag's
        # sort_axis) looked identical to the clearest cases, and a cast full
        # of near-identical entries lost all texture. Reuses the exact same
        # sorted+tier-marker shape/parsing rank() already uses for ordinals
        # (see collection.py's scores_from_result/parse_sorted), just with a
        # fixed 3-tier scale instead of a param-specific one: T1=doesn't
        # have it, T2=unsure, T3=clearly has it — still 1 pass, not 2 (cost
        # stays down), but the model now gets a real "unsure" answer instead
        # of being forced into a binary yes/no it wasn't confident about,
        # plus its own separate "unknown" list for characters it doesn't
        # recognize at all (system_prompt_flag_rank.j2's rule 6 — a
        # different kind of not-knowing than "unsure about this trait").
        flag_def = get_flag_def(flag_name)
        system_prompt = get_prompt("system_prompt_flag_rank", time_period=arc or "entire series")
        user_prompt = get_prompt(
            "user_prompt_flag_rank",
            flag_name=flag_name,
            flag_definition=flag_def["definition"],
            flag_sort_axis=flag_def["sort_axis"],
            universe=universe,
            time_period=arc or "entire series",
            characters=characters,
            context=context,
        )
        result = self._request(
            response_model=FlagRankResponse,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            # Model in the key prefix: the key is otherwise built purely from
            # prompt text, so swapping model_flag would silently keep serving
            # the previous model's cached answers instead of ever calling the
            # new one. Prefix stays "flag" up to the first colon, which is
            # all token_usage's call_type reads.
            cache_key=prompt_cache_key(f"flag:{self.model_flag}", system_prompt, user_prompt, pass_number),
            model=self.model_flag,
            thinking=self.thinking_flag if self.thinking_flag is not None else thinking_for(characters),
            temperature=self.temperature_flag,
            force_refresh=force_refresh,
        )
        return result.model_dump()

    def profile(self, characters: list[str], universe: str, arc: str | None = None, context: str | None = None, ) -> dict:
        system_prompt = get_prompt("system_prompt_profiler")
        user_prompt = get_prompt("user_prompt_profiler", universe=universe, characters=characters, arc=arc, context=context)
        result = self._request(
            response_model=ProfileResponse,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cache_key=prompt_cache_key("profile", system_prompt, user_prompt),
            model=self.model_profile,
            thinking=self.thinking_profile,
            temperature=self.temperature_profile,
        )
        return {"characters": {c.name: c.model_dump(exclude={"name"}) for c in result.characters}}

    # characters (both methods below): an external ground-truth cast list
    # (AniList, see services/collection/cast/anime_db.py), not derived from
    # this pipeline's own prior output — the old "no list, groups produce
    # the roster" design was a real chicken-and-egg constraint before an
    # independent source existed. Given as a reference to check recall and
    # prefer exact spelling against, not a hard cap: the prompt still
    # allows naming someone not on it (the list may be incomplete for
    # minor characters), same as before. Optional and defaulted to None so
    # a universe with no AniList match still collects blind, same as
    # always.

    def group_medium(self, universe: str, arc: str | None = None, context: str | None = None,
                      location: str | None = None, characters: list[str] | None = None) -> dict:
        # Its own dedicated call, 1 pass — was 2 passes. Kept separate from
        # large/isolates (not folded into one combined prompt): medium's
        # definition ("everyone knows everyone") and large's ("members are
        # strangers") are near-opposites, and asking both in the same
        # prompt risks the model blurring the boundary between them
        # (2026-09-23, explicit call: "2 промпта отдельных", not 1 combined).
        system_prompt = get_prompt("system_prompt_groups", universe=universe, time_period=arc or "entire series")
        user_prompt = get_prompt(
            "user_prompt_groups_medium",
            universe=universe,
            time_period=arc or "entire series",
            location=location,
            context=context,
            characters=characters,
        )
        result = self._request(
            response_model=GroupsResponse,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cache_key=prompt_cache_key("group_medium", system_prompt, user_prompt),
            model=self.model_group,
            thinking=self.thinking_group,
            temperature=self.temperature_group,
        )
        return result.model_dump()

    def group_large_isolates(self, universe: str, arc: str | None = None, context: str | None = None,
                              location: str | None = None, characters: list[str] | None = None) -> dict:
        # large groups + isolates combined into 1 call, 1 pass — was 2
        # separate calls (isolates had its own IsolatesResponse call) x 2
        # passes each (4 calls); cut to 1. Safe to combine (unlike medium,
        # see group_medium's docstring): "large group membership" and
        # "has no personal ties" are unrelated axes, not opposites that
        # could bleed into each other — a character can be in a huge faction
        # and still be an isolate within it, the prompt says so explicitly.
        # GroupsResponse already carries both `groups` (tagged group_type)
        # and `isolates` fields, so no schema change was needed.
        system_prompt = get_prompt("system_prompt_groups", universe=universe, time_period=arc or "entire series")
        user_prompt = get_prompt(
            "user_prompt_groups_large_isolates",
            universe=universe,
            time_period=arc or "entire series",
            location=location,
            context=context,
            characters=characters,
        )
        result = self._request(
            response_model=GroupsResponse,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cache_key=prompt_cache_key("group_large_isolates", system_prompt, user_prompt),
            model=self.model_group,
            thinking=self.thinking_group,
            temperature=self.temperature_group,
        )
        return result.model_dump()

    def relations(self, relation_type: str, characters: list[str],
                  universe: str, arc: str | None = None, context: str | None = None,
                  pass_number: int | None = None, temperature: float | None = None) -> dict:
        if relation_type not in RELATION_TYPES:
            raise falseRelationTypeException()

        directed = RELATION_TYPES[relation_type] == "directed"
        system_prompt = get_prompt("system_prompt_relations")
        user_prompt = get_prompt(
            f"user_prompt_rel_{relation_type}",
            universe=universe,
            time_period=arc or "entire series",
            characters=characters,
            context=context,
        )
        result = self._request(
            response_model=DirectedResponse if directed else SymmetricResponse,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cache_key=prompt_cache_key("relation", system_prompt, user_prompt, pass_number),
            model=self.model_relation,
            thinking=self.thinking_relation,
            temperature=self.temperature_relation if temperature is None else temperature,
        )
        return result.model_dump()

    def alias_names(self, names: list[str], universe: str, arc: str | None = None,
                     context: str | None = None, pass_number: int | None = None) -> dict:
        system_prompt = get_prompt("system_prompt_alias")
        user_prompt = get_prompt(
            "user_prompt_alias_names",
            universe=universe,
            time_period=arc or "entire series",
            names=names,
            context=context,
        )
        result = self._request(
            response_model=AliasNamesResponse,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cache_key=prompt_cache_key("alias", system_prompt, user_prompt, pass_number),
            model=self.model_alias,
            thinking=self.thinking_alias,
            temperature=self.temperature_alias,
        )
        return result.model_dump()

    def group_relations(self, kind: str, groups: list[dict], universe: str,
                         arc: str | None = None) -> dict:
        if kind not in GROUP_RELATION_DESC:
            raise falseRelationTypeException()

        system_prompt = get_prompt("system_prompt_group_relations", relation_desc=GROUP_RELATION_DESC[kind])
        user_prompt = get_prompt(
            "user_prompt_group_relations",
            universe=universe,
            time_period=arc or "entire series",
            relation_desc=GROUP_RELATION_DESC[kind],
            groups=groups,
        )
        result = self._request(
            response_model=GroupPairsResponse,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cache_key=prompt_cache_key("group_relations", system_prompt, user_prompt),
            model=self.model_group_relations,
            thinking=self.thinking_group_relations,
            temperature=self.temperature_group_relations,
        )
        return result.model_dump()

    def group_hierarchy(self, groups: list[dict], universe: str, arc: str | None = None) -> dict:
        # Directional (child, parent) — a separate call from group_relations
        # (allied/rival), which is symmetric and explicitly skips
        # containment. Same schema (GroupPairsResponse), same one-call-per-
        # universe shape as group_relations.
        system_prompt = get_prompt("system_prompt_group_hierarchy")
        user_prompt = get_prompt(
            "user_prompt_group_hierarchy",
            universe=universe,
            time_period=arc or "entire series",
            groups=groups,
        )
        result = self._request(
            response_model=GroupPairsResponse,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cache_key=prompt_cache_key("group_hierarchy", system_prompt, user_prompt),
            model=self.model_group_relations,
            thinking=self.thinking_group_relations,
            temperature=self.temperature_group_relations,
        )
        return result.model_dump()

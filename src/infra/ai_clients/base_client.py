from abc import ABC, abstractmethod
from typing import TypeVar
from pydantic import BaseModel
from src.infra.prompts.loader import get_prompt
from src.infra.ai_clients.schemas.ranker_schema import RankingResponse
from src.infra.ai_clients.schemas.profiler_schema import ProfileResponse
from src.infra.ai_clients.schemas.groups_schema import GroupsResponse, IsolatesResponse
from src.infra.ai_clients.schemas.relations_schema import SymmetricResponse, DirectedResponse
from src.infra.ai_clients.schemas.alias_schema import AliasNamesResponse
from src.infra.ai_clients.schemas.group_relations_schema import GroupPairsResponse
from src.infra.exceptions import falseGroupTypeException, falseRelationTypeException
from src.domain.parameters import FLAG_PARAMS
import json
import hashlib

T = TypeVar("T", bound=BaseModel)

CACHE_TTL = 60 * 60 * 24 * 14
GROUP_TYPES = {"small", "medium", "large", "isolates"}
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
    return min(2048 + 64 * len(characters), 16384)


def get_flag_def(name: str) -> dict:
    # FLAG_PARAMS is the single source of truth (src/domain/parameters.py) —
    # flattened once from parameters.json, not re-read here.
    if name not in FLAG_PARAMS:
        raise ValueError(f"Flag '{name}' not found in parameters.json")
    return FLAG_PARAMS[name]


class BaseAIClient(ABC):

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
        )
        return result.model_dump()

    def flag(self, flag_name: str, characters: list[str],
                universe: str, arc: str | None = None, context: str | None = None,
                pass_number: int | None = None) -> dict:
        flag_def = get_flag_def(flag_name)
        system_prompt = get_prompt("system_prompt_flagger", time_period=arc or "entire series")
        user_prompt = get_prompt(
            "user_prompt_flagger",
            flag_name=flag_name,
            flag_definition=flag_def["definition"],
            flag_sort_axis=flag_def["sort_axis"],
            universe=universe,
            time_period=arc or "entire series",
            characters=characters,
            context=context,
        )
        result = self._request(
            response_model=RankingResponse,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cache_key=prompt_cache_key("flag", system_prompt, user_prompt, pass_number),
            model=self.model_flag,
            thinking=thinking_for(characters),
            temperature=self.temperature_flag,
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

    def group(self, group_type: str, universe: str, arc: str | None = None,
              context: str | None = None, pass_number: int | None = None,
              location: str | None = None, characters: list[str] | None = None) -> dict:
        if group_type not in GROUP_TYPES:
            raise falseGroupTypeException()

        # characters: an external ground-truth cast list (AniList, see
        # services/collection/cast/anime_db.py), not derived from this
        # pipeline's own prior output — the old "no list, groups produce
        # the roster" design was a real chicken-and-egg constraint before
        # an independent source existed. Given as a reference to check
        # recall and prefer exact spelling against, not a hard cap: the
        # prompt still allows naming someone not on it (the list may be
        # incomplete for minor characters), same as before. Optional and
        # defaulted to None so a universe with no AniList match still
        # collects blind, same as always.
        response_model = IsolatesResponse if group_type == "isolates" else GroupsResponse

        system_prompt = get_prompt("system_prompt_groups", universe=universe, time_period=arc or "entire series")
        user_prompt = get_prompt(
            f"user_prompt_groups_{group_type}",
            universe=universe,
            time_period=arc or "entire series",
            location=location,
            context=context,
            characters=characters,
        )
        result = self._request(
            response_model=response_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            cache_key=prompt_cache_key("group", system_prompt, user_prompt, pass_number),
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

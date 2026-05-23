from abc import ABC, abstractmethod
from typing import TypeVar
from pydantic import BaseModel
from app.data.data import get_prompt
from app.apiClients.schemas.ranker_schema import RankingResponse
from app.apiClients.schemas.profiler_schema import ProfileResponse
import json
import hashlib
from pathlib import Path

T = TypeVar("T", bound=BaseModel)

CACHE_TTL = 60 * 60 * 24
FLAGS_PATH = Path("app/data/flags.json")

_flags_cache: dict | None = None


def _get_flags() -> dict:
    global _flags_cache
    if _flags_cache is None:
        with open(FLAGS_PATH, "r", encoding="utf-8") as f:
            _flags_cache = json.load(f)
    return _flags_cache


def hash_args(*args) -> str:
    return hashlib.sha256(
        json.dumps(args, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def get_flag_def(name: str) -> dict:
    for cat_name, cat in _get_flags().items():
        if cat_name.startswith("_"):
            continue
        if name in cat:
            return cat[name]
    raise ValueError(f"Flag '{name}' not found in flags.json")


class BaseAIClient(ABC):

    @abstractmethod
    def _request(
        self,
        response_model: type[T],
        system_prompt: str,
        user_prompt: str,
        cache_key: str,
        model: str,
        thinking_budget: int = 0,
    ) -> T:
        ...

    def rank(
        self,
        prompt: str,
        characters: list[str],
        universe: str,
        arc: str | None = None,
        context: str | None = None,
    ) -> dict:
        result = self._request(
            response_model=RankingResponse,
            system_prompt=get_prompt("system_prompt_ranker"),
            user_prompt=get_prompt(prompt, universe=universe, characters=characters, arc=arc, context=context),
            cache_key=f"rank:{hash_args(prompt, characters, universe, arc, context)}",
            model=self.model_rank,
            thinking_budget=self.thinking_rank,
        )
        return result.model_dump()

    def flag(
        self,
        flag_name: str,
        characters: list[str],
        universe: str,
        arc: str | None = None,
        context: str | None = None,
    ) -> dict:
        flag_def = get_flag_def(flag_name)
        result = self._request(
            response_model=RankingResponse,
            system_prompt=get_prompt("system_prompt_flagger"),
            user_prompt=get_prompt(
                "user_prompt_flagger",
                flag_name=flag_name,
                flag_definition=flag_def["definition"],
                flag_sort_axis=flag_def["sort_axis"],
                universe=universe,
                time_period=arc or "entire series",
                characters=characters,
                context=context,
            ),
            cache_key=f"flag:{hash_args(flag_name, characters, universe, arc, context)}",
            model=self.model_flag,
            thinking_budget=self.thinking_flag,
        )
        return result.model_dump()

    def profile(
        self,
        characters: list[str],
        universe: str,
        arc: str | None = None,
        context: str | None = None,
    ) -> dict:
        result = self._request(
            response_model=ProfileResponse,
            system_prompt=get_prompt("system_prompt_profiler"),
            user_prompt=get_prompt("user_prompt_profiler", universe=universe, characters=characters, arc=arc, context=context),
            cache_key=f"profile:{hash_args('profiler', characters, universe, arc, context)}",
            model=self.model_profile,
            thinking_budget=self.thinking_profile,
        )
        return {"characters": {c.name: c.model_dump(exclude={"name"}) for c in result.characters}}

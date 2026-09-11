import functools
from typing import TypeVar
from pydantic import BaseModel
from google import genai
from google.genai import types
from src.infra.settings.config import Settings
from src.infra.settings.redis_client import redis_cache
from src.infra.ai_clients.base_client import BaseAIClient, CACHE_TTL

T = TypeVar("T", bound=BaseModel)

_settings = Settings()


class GeminiClient(BaseAIClient):

    model_rank            = "gemini-3.8-flash"
    model_flag             = "gemini-3.1-flash-lite"
    model_profile          = "gemini-3.1-flash-lite"
    model_group            = "gemini-3.8-flash"
    model_relation         = "gemini-3.8-flash"
    model_alias            = "gemini-3.8-flash"
    model_group_relations  = "gemini-3.8-flash"

    # thinking: gemini-3.8-flash (rank/group/relation/alias/group_relations)
    # only accepts thinking_level, not thinking_budget — "minimal" errors on
    # this model. flag stays on gemini-3.1-flash-lite, still numeric
    # thinking_budget, scaled by roster size via base_client.thinking_for().
    # profile stays flat 0 = off.
    thinking_rank            = "low"
    thinking_profile         = 0
    thinking_group           = "low"
    thinking_relation        = "low"
    thinking_alias           = "low"
    thinking_group_relations = "low"

    # temperature per task type
    temperature_rank            = _settings.temperature
    temperature_flag            = _settings.temperature
    temperature_profile         = _settings.temperature
    temperature_group           = 0.4
    temperature_relation        = 0.4
    temperature_alias           = 0.4
    temperature_group_relations = 0.0

    def __init__(self) -> None:
        self._client = genai.Client(api_key=_settings.api_key_gimini)

    def __cached(fn):
        """Cross-cutting: check Redis before calling the model, write the
        result back after. The wrapped method only ever builds the request
        and calls Gemini — it never touches the cache itself."""
        @functools.wraps(fn)
        def wrapper(self, response_model, system_prompt, user_prompt, cache_key,
                    model, thinking=0, temperature=0.1):
            cached = redis_cache.get(cache_key)
            if cached:
                return response_model.model_validate_json(cached)
            result = fn(self, response_model, system_prompt, user_prompt, cache_key,
                        model, thinking, temperature)
            redis_cache.set(cache_key, result.model_dump_json(), ex=CACHE_TTL)
            return result
        return wrapper

    @__cached
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
        if isinstance(thinking, str):
            thinking_config = types.ThinkingConfig(thinking_level=getattr(types.ThinkingLevel, thinking.upper()))
        else:
            thinking_config = types.ThinkingConfig(thinking_budget=thinking)

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=response_model,
            max_output_tokens=65536,  # model ceiling (gemini-3.8-flash) — 32768 was truncating alias_names
                                       # once the candidate list grew large enough that thinking + JSON output
                                       # together exceeded it (same cutoff point on 2 separate runs, not transient)
            temperature=temperature,
            thinking_config=thinking_config,
        )

        response = self._client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=config,
        )

        return response_model.model_validate_json(response.text)

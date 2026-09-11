import functools
from typing import TypeVar
from pydantic import BaseModel
from xai_sdk import Client
from xai_sdk.chat import user, system
from src.infra.settings.config import Settings
from src.infra.settings.redis_client import redis_cache
from src.infra.ai_clients.base_client import BaseAIClient, CACHE_TTL

T = TypeVar("T", bound=BaseModel)

_settings = Settings()


def flush_flag_cache() -> int:
    keys = redis_cache.keys("flag:*")
    if keys:
        redis_cache.delete(*keys)
    return len(keys)


class XClient(BaseAIClient):

    model_rank            = "grok-4-1-fast-reasoning"
    model_flag             = "grok-4-1-fast-reasoning"
    model_profile          = "grok-4-1-fast-reasoning"
    model_group            = "grok-4-1-fast-reasoning"
    model_relation         = "grok-4-1-fast-reasoning"
    model_alias            = "grok-4-1-fast-reasoning"
    model_group_relations  = "grok-4-1-fast-reasoning"

    thinking_rank            = 0
    thinking_profile         = 0
    thinking_group           = 0
    thinking_relation        = 0
    thinking_alias           = 0
    thinking_group_relations = 0

    temperature_rank            = _settings.temperature
    temperature_flag            = _settings.temperature
    temperature_profile         = _settings.temperature
    temperature_group           = 0.4
    temperature_relation        = 0.4
    temperature_alias           = 0.4
    temperature_group_relations = 0.0

    def __init__(self) -> None:
        self._client = Client(_settings.api_key_x)

    def __cached(fn):
        """Cross-cutting: check Redis before calling the model, write the
        result back after — same convention as GeminiClient."""
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
        chat = self._client.chat.create(
            model=model,
            response_format=response_model,
            max_tokens=32768,
        )
        chat.append(system(system_prompt))
        chat.append(user(user_prompt))

        return response_model.model_validate_json(chat.sample().content)

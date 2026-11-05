"""CerebrasClient — free-tier alternative to GeminiClient, used only for the
one-off model-quality comparison (src/experiments/compare_models.py). Not
wired into the real pipeline. Cerebras exposes an OpenAI-compatible
endpoint, so this reuses the `openai` package already in analyse.yml — no
new dependency — and every existing prompt/schema BaseAIClient's rank()/
flag()/etc. already build works here unchanged.

Cache-key note: BaseAIClient.rank()/flag()/... build the Redis cache key
from prompt content alone (prompt_cache_key), not from which client/model
is calling — so a raw pass-through would silently return GeminiClient's
already-cached answer for an identical prompt instead of ever calling
Cerebras. __cached below prefixes the key with "cerebras:" to keep this
client's cache entries in their own namespace, isolated from Gemini's.
"""
import functools
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from src.infra.ai_clients.base_client import BaseAIClient, CACHE_TTL
from src.infra.settings.config import Settings
from src.infra.settings.redis_client import redis_cache

T = TypeVar("T", bound=BaseModel)

_settings = Settings()


class CerebrasClient(BaseAIClient):

    model_rank            = "gpt-oss-120b"
    model_flag             = "gpt-oss-120b"
    model_profile          = "gpt-oss-120b"
    model_group            = "gpt-oss-120b"
    model_relation         = "gpt-oss-120b"
    model_alias            = "gpt-oss-120b"
    model_group_relations  = "gpt-oss-120b"

    # gpt-oss-120b's reasoning effort isn't exposed the same way as Gemini's
    # thinking_level/thinking_budget — left unused here; this client exists
    # only for a one-off quality comparison, not production tuning.
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
        self._client = OpenAI(base_url="https://api.cerebras.ai/v1", api_key=_settings.cerebras_api_key)

    def __cached(fn):
        @functools.wraps(fn)
        def wrapper(self, response_model, system_prompt, user_prompt, cache_key,
                    model, thinking=0, temperature=0.1):
            namespaced_key = f"cerebras:{model}:{cache_key}"
            cached = redis_cache.get(namespaced_key)
            if cached:
                return response_model.model_validate_json(cached)
            result = fn(self, response_model, system_prompt, user_prompt, cache_key,
                        model, thinking, temperature)
            redis_cache.set(namespaced_key, result.model_dump_json(), ex=CACHE_TTL)
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
        schema = response_model.model_json_schema()
        schema["additionalProperties"] = False  # required by strict json_schema mode

        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": response_model.__name__, "strict": True, "schema": schema},
            },
        )
        return response_model.model_validate_json(response.choices[0].message.content)

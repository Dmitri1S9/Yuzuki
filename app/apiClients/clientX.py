from typing import TypeVar
from pydantic import BaseModel
from xai_sdk import Client
from xai_sdk.chat import user, system
from app.settings.config import Settings
from app.settings.redis import redis_cache
from app.apiClients.base_client import BaseAIClient, CACHE_TTL

T = TypeVar("T", bound=BaseModel)

_settings = Settings()


def flush_flag_cache() -> int:
    keys = redis_cache.keys("flag:*")
    if keys:
        redis_cache.delete(*keys)
    return len(keys)


class XClient(BaseAIClient):

    def __init__(self) -> None:
        self._client = Client(_settings.api_key_x)

    def _request(
        self,
        response_model: type[T],
        system_prompt: str,
        user_prompt: str,
        cache_key: str,
    ) -> T:
        cached = redis_cache.get(cache_key)
        if cached:
            return response_model.model_validate_json(cached)

        chat = self._client.chat.create(
            model="grok-4-1-fast-reasoning",
            response_format=response_model,
            max_tokens=32768,
        )
        chat.append(system(system_prompt))
        chat.append(user(user_prompt))

        result = response_model.model_validate_json(chat.sample().content)
        redis_cache.set(cache_key, result.model_dump_json(), ex=CACHE_TTL)
        return result

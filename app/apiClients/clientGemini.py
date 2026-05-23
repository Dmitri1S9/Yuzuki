from typing import TypeVar
from pydantic import BaseModel
from google import genai
from google.genai import types
from app.settings.config import Settings
from app.settings.redis import redis_cache
from app.apiClients.base_client import BaseAIClient, CACHE_TTL

T = TypeVar("T", bound=BaseModel)

_settings = Settings()


class GeminiClient(BaseAIClient):

    model_rank    = "gemini-3.5-flash"
    model_flag    = "gemini-3.1-flash-lite"
    model_profile = "gemini-3.1-flash-lite"

    # thinking budget per task type: 0 = off
    thinking_rank    = 1024
    thinking_flag    = 0
    thinking_profile = 0

    def __init__(self) -> None:
        self._client = genai.Client(api_key=_settings.api_key_gimini)

    def _request(
        self,
        response_model: type[T],
        system_prompt: str,
        user_prompt: str,
        cache_key: str,
        model: str,
        thinking_budget: int = 0,
    ) -> T:
        cached = redis_cache.get(cache_key)
        if cached:
            return response_model.model_validate_json(cached)

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=response_model,
            max_output_tokens=32768,
            temperature=0.1,
            thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
        )

        response = self._client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=config,
        )

        result = response_model.model_validate_json(response.text)
        redis_cache.set(cache_key, result.model_dump_json(), ex=CACHE_TTL)
        return result

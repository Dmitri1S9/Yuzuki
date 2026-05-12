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

    def __init__(self) -> None:
        self._client = genai.Client(api_key=_settings.api_key_gemini)

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

        response = self._client.models.generate_content(
            model="gemini-2.5-pro",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=response_model,
                max_output_tokens=32768,
            ),
        )

        result = response_model.model_validate_json(response.text)
        redis_cache.set(cache_key, result.model_dump_json(), ex=CACHE_TTL)
        return result

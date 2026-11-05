import functools
from typing import TypeVar
from pydantic import BaseModel
from google import genai
from google.genai import types
from src.infra.settings.config import Settings
from src.infra.settings.redis_client import redis_cache
from src.infra.ai_clients.base_client import BaseAIClient, CACHE_TTL
from src.infra.token_usage import log_token_usage

T = TypeVar("T", bound=BaseModel)

_settings = Settings()


class GeminiClient(BaseAIClient):

    model_rank            = "gemini-3.8-flash"
    model_flag             = "gemini-3.8-flash"
    model_profile          = "gemini-3.1-flash-lite"
    model_group            = "gemini-3.8-flash"
    model_relation         = "gemini-3.8-flash"
    model_alias            = "gemini-3.8-flash"
    model_group_relations  = "gemini-3.8-flash"

    # thinking: gemini-3.8-flash (rank/flag/group/relation/alias/group_relations)
    # only accepts thinking_level, not thinking_budget — "minimal" errors on
    # this model. flag moved from gemini-3.1-flash-lite (numeric budget
    # scaled by roster size, base_client.thinking_for()) to 3.8-flash "low"
    # on 2026-09-23 as an experiment — see the flag-model comparison for why;
    # to go back, set model_flag to flash-lite and thinking_flag to None
    # (falls back to thinking_for). profile stays flat 0 = off.
    thinking_rank            = "low"
    thinking_flag            = "low"
    thinking_profile         = 0
    thinking_group           = "low"
    thinking_relation        = "low"
    thinking_alias           = "low"
    thinking_group_relations = "low"

    # temperature per task type. group/alias were 0.4 to diversify across
    # multiple passes (a later pass needed a chance at a different answer to
    # corroborate against) — now single-pass (see cast/constants.py), so
    # there is no second pass to diversify against and 0 is the better bet,
    # same reasoning as group_relations below.
    temperature_rank            = _settings.temperature
    # 0.0, not the shared setting (2026-09-23): live-caught on Bunny Girl
    # Senpai — 14/51 flags on that (smaller, 20-character) roster came back
    # with EVERY character in "unknown" despite a same-day, same-prompt
    # rerun of one of them ("manipulative") landing real placements for
    # most of the cast. At temperature 0.1 that's not just calibrated
    # caution, it's response-to-response variance flipping a call between
    # "confident" and "fully conservative" — flags get only 1 pass with no
    # cross-pass reconciliation to catch that, unlike ordinals' 2, so there
    # is nothing here to average the noise out. 0 doesn't guarantee
    # determinism (still real sampling under the hood) but removes the one
    # knob under this system's control that was adding to it.
    temperature_flag            = 0.0
    temperature_profile         = _settings.temperature
    temperature_group           = 0.0
    temperature_relation        = 0.4
    temperature_alias           = 0.0
    temperature_group_relations = 0.0

    def __init__(self) -> None:
        self._client = genai.Client(api_key=_settings.api_key_gimini)

    def __cached(fn):
        """Cross-cutting: check Redis before calling the model, write the
        result back after. The wrapped method only ever builds the request
        and calls Gemini — it never touches the cache itself.

        force_refresh: skips the read (always calls Gemini for real), still
        writes the fresh result back — a schema-valid-but-substantively-
        broken response (see collection.py's completeness check, added
        2026-09-23) gets cached here exactly like a good one, since this
        layer only knows Pydantic validity, not roster-completeness
        semantics. Without a way to bypass the read on retry, a caller
        that detected a bad response and asked again would just get the
        same broken response handed back from Redis, making the retry a
        no-op — this is what makes a real second attempt possible."""
        @functools.wraps(fn)
        def wrapper(self, response_model, system_prompt, user_prompt, cache_key,
                    model, thinking=0, temperature=0.1, force_refresh=False):
            if not force_refresh:
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

        # Real usage, not the prompt-shape-based guesses used before this —
        # only reached on an actual API call (this method sits inside
        # __cached, so a cache hit never gets here, correctly logging
        # nothing for a call that cost nothing). call_type recovered from
        # cache_key's own "{prefix}:{digest}" format (prompt_cache_key) —
        # no new parameter needed just for this.
        usage = response.usage_metadata
        if usage is not None:
            call_type = cache_key.split(":", 1)[0]
            log_token_usage(
                call_type=call_type,
                model=model,
                prompt_tokens=usage.prompt_token_count or 0,
                output_tokens=usage.candidates_token_count or 0,
                thinking_tokens=usage.thoughts_token_count or 0,
                total_tokens=usage.total_token_count or 0,
            )

        return response_model.model_validate_json(response.text)

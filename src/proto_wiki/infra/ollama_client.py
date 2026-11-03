"""The only Ollama client in the prototype — the external, atomic service
class (this prototype's one-per-provider slot, mirroring how the main
pipeline has one class per LLM provider under src/infra/ai_clients/, though
this is its own separate service and not literally that package).

Every call is schema-constrained (Pydantic JSON schema -> `format`),
temperature 0, thinking off. A call that cannot produce a valid answer
raises LLMError — callers must record that as an error, never as an
empty/unknown answer.

The retry/VRAM-offload log lines below are the one deliberate exception to
"no logging on external/service classes": they are this service's own
operational diagnostics (network retries, GPU memory state), not narration
of a workhorse's business step, so there is nothing else to decorate them
onto — a decision made explicitly, not an oversight (see src/shared/
decorators.py's equivalent note on ai_clients having zero logging, which
this class deliberately does not match for this one reason).
"""
import logging
import os
import time
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

FALLBACK_CTX = 16384
_KEEP_ALIVE = "30m"


class LLMError(Exception):
    pass


class _Truncated(LLMError):
    """Deterministic, so not worth retrying."""


class OllamaClient:
    def __init__(self, model: str, ctx: int = 32768, host: str | None = None, timeout: float = 900.0,
                 retries: int = 3, num_predict: int = 4096, sleep=time.sleep, transport=None):
        host = host or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
        if "://" not in host:
            host = f"http://{host}"
        self.model = model
        self.ctx = ctx
        self.retries = retries
        self.num_predict = num_predict
        self._sleep = sleep
        self._send_think = True
        self._http = httpx.Client(base_url=host.rstrip("/"), timeout=timeout, transport=transport)

    # --- generation ---------------------------------------------------------

    def generate(self, system: str, user: str, response_model: type[T]) -> T:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "format": response_model.model_json_schema(),
            "keep_alive": _KEEP_ALIVE,
        }
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return self._once(payload, response_model)
            except _Truncated as e:
                raise LLMError(str(e)) from e
            except (httpx.HTTPError, ValidationError, KeyError, TypeError, ValueError) as e:
                last = e
                log.warning("Вызов LLM не удался (попытка %d/%d): %s", attempt + 1, self.retries + 1, _short(e))
                if attempt < self.retries:
                    self._sleep(2 ** attempt)
        raise LLMError(f"после {self.retries} ретраев: {_short(last)}") from last

    def _once(self, payload: dict, response_model: type[T]) -> T:
        data = self._chat(payload)
        # Ollama silently drops the start of a prompt that does not fit
        # num_ctx; a "valid" answer then comes from a text with a hole in it.
        if (data.get("prompt_eval_count") or 0) >= self.ctx:
            raise _Truncated(
                f"промпт не поместился в контекст {self.ctx} токенов (prompt_eval_count={data['prompt_eval_count']})"
            )
        return response_model.model_validate_json(data["message"]["content"])

    def _chat(self, payload: dict) -> dict:
        body = {**payload, "options": {"temperature": 0, "num_ctx": self.ctx, "num_predict": self.num_predict}}
        if self._send_think:
            body["think"] = False
        resp = self._http.post("/api/chat", json=body)
        if resp.status_code == 400 and self._send_think:
            log.warning("Модель не принимает think — повторяю запрос без этого поля")
            self._send_think = False
            body.pop("think")
            resp = self._http.post("/api/chat", json=body)
        resp.raise_for_status()
        return resp.json()

    # --- startup: load the model and make sure it fits in VRAM ---------------

    def ensure_loaded(self) -> None:
        try:
            self._load()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise LLMError(f"Модель {self.model} не найдена в Ollama — сделайте `ollama pull {self.model}`") from e
            raise LLMError(f"Ollama вернула ошибку при загрузке модели: {_short(e)}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama недоступна ({self._http.base_url}): {_short(e)}. Запущена ли служба?") from e

        offloaded = self._cpu_offload()
        if offloaded and self.ctx > FALLBACK_CTX:
            log.warning("Модель частично выгружена на CPU при ctx=%d — снижаю контекст до %d",
                        self.ctx, FALLBACK_CTX)
            self.ctx = FALLBACK_CTX
            self._load()
            offloaded = self._cpu_offload()
        if offloaded:
            log.warning("Модель всё ещё не целиком в VRAM (ctx=%d) — расчёт будет медленным", self.ctx)
        else:
            log.info("Модель %s целиком в VRAM, ctx=%d", self.model, self.ctx)

    def _load(self) -> None:
        resp = self._http.post("/api/chat", json={
            "model": self.model, "messages": [], "keep_alive": _KEEP_ALIVE, "options": {"num_ctx": self.ctx},
        })
        resp.raise_for_status()

    def _cpu_offload(self) -> bool:
        """True if part of the loaded model sits in system RAM. None-safe:
        if /api/ps does not list the model, assume it fits."""
        try:
            models = self._http.get("/api/ps").json().get("models", [])
        except (httpx.HTTPError, ValueError):
            return False
        for m in models:
            if m.get("name") == self.model or m.get("model") == self.model:
                size, vram = m.get("size") or 0, m.get("size_vram") or 0
                return size > 0 and vram < size * 0.99
        return False


def _short(e: Exception | None) -> str:
    text = " ".join(str(e).split())
    return f"{type(e).__name__}: {text[:300]}"

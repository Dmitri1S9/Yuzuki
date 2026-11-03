"""Ollama /api/chat, schema-constrained. Atomic external class: no logging, no
business logic. Metrics and attempt count come back in the result; a call that
cannot produce a valid answer raises LLMError carrying the raw text and metrics.
"""
import os
import time
from dataclasses import dataclass
from typing import Generic, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)
_NS_TO_MS = 1e-6


@dataclass(frozen=True)
class CallMetrics:
    prompt_eval_count: int = 0
    prompt_eval_ms: float = 0.0
    eval_count: int = 0
    eval_ms: float = 0.0
    total_ms: float = 0.0
    load_ms: float = 0.0
    attempts: int = 1


@dataclass(frozen=True)
class ChatResult(Generic[T]):
    parsed: T
    raw: str
    metrics: CallMetrics


class LLMError(Exception):
    def __init__(self, message: str, raw: str = "", metrics: CallMetrics | None = None):
        super().__init__(message)
        self.raw = raw
        self.metrics = metrics or CallMetrics()


class PromptTooLong(LLMError):
    """Deterministic (Ollama silently drops the start of an over-long prompt) — never retried."""


class OllamaClient:
    def __init__(self, model: str, num_ctx: int, num_predict: int, keep_alive: str = "30m",
                 timeout_s: float = 900.0, retries: int = 2, host: str | None = None,
                 sleep=time.sleep, transport=None):
        host = host or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
        if "://" not in host:
            host = f"http://{host}"
        self.model = model
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.keep_alive = keep_alive
        self.retries = retries
        self._sleep = sleep
        self._send_think = True
        self._http = httpx.Client(base_url=host.rstrip("/"), timeout=timeout_s, transport=transport)

    def chat(self, prompt: str, response_model: type[T], temperature: float = 0.0,
             num_predict: int | None = None) -> ChatResult[T]:
        num_predict = num_predict or self.num_predict
        last_error = ""
        raw = ""
        metrics = CallMetrics()
        for attempt in range(1, self.retries + 2):
            try:
                data = self._post(prompt, response_model, temperature, num_predict)
            except httpx.HTTPError as e:
                last_error = f"{type(e).__name__}: {_short(e)}"
            else:
                metrics = _metrics(data, attempt)
                raw = data.get("message", {}).get("content", "")
                if metrics.prompt_eval_count > self.num_ctx - num_predict:
                    raise PromptTooLong(
                        f"prompt does not fit num_ctx={self.num_ctx} (prompt_eval_count={metrics.prompt_eval_count})",
                        raw, metrics)
                if data.get("done_reason") == "length":
                    # temperature 0 is deterministic: retrying a cut-off answer gives the same cut-off
                    raise LLMError(f"answer cut at num_predict={num_predict}", raw, metrics)
                try:
                    return ChatResult(response_model.model_validate_json(raw), raw, metrics)
                except ValidationError as e:
                    last_error = f"invalid answer: {_short(e)}"
            if attempt <= self.retries:
                self._sleep(2 ** (attempt - 1))
        raise LLMError(f"after {self.retries + 1} attempts: {last_error}", raw, metrics)

    def _post(self, prompt: str, response_model: type[BaseModel], temperature: float, num_predict: int) -> dict:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": response_model.model_json_schema(),
            "keep_alive": self.keep_alive,
            "options": {"temperature": temperature, "num_ctx": self.num_ctx, "num_predict": num_predict},
        }
        if self._send_think:
            body["think"] = False
        resp = self._http.post("/api/chat", json=body)
        if resp.status_code == 400 and self._send_think:
            self._send_think = False
            body.pop("think")
            resp = self._http.post("/api/chat", json=body)
        resp.raise_for_status()
        return resp.json()

    def load(self) -> bool:
        """Loads the model with this num_ctx. Returns True when it sits fully in VRAM."""
        self._http.post("/api/chat", json={
            "model": self.model, "messages": [], "keep_alive": self.keep_alive,
            "options": {"num_ctx": self.num_ctx}}).raise_for_status()
        for m in self._http.get("/api/ps").json().get("models", []):
            if self.model in (m.get("name"), m.get("model")):
                size, vram = m.get("size") or 0, m.get("size_vram") or 0
                return size > 0 and vram >= size * 0.99
        return True

    def close(self) -> None:
        self._http.close()


def _metrics(data: dict, attempt: int) -> CallMetrics:
    return CallMetrics(
        prompt_eval_count=int(data.get("prompt_eval_count") or 0),
        prompt_eval_ms=(data.get("prompt_eval_duration") or 0) * _NS_TO_MS,
        eval_count=int(data.get("eval_count") or 0),
        eval_ms=(data.get("eval_duration") or 0) * _NS_TO_MS,
        total_ms=(data.get("total_duration") or 0) * _NS_TO_MS,
        load_ms=(data.get("load_duration") or 0) * _NS_TO_MS,
        attempts=attempt,
    )


def _short(e: Exception) -> str:
    return " ".join(str(e).split())[:300]

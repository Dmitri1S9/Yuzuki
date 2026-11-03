"""Минимальный клиент Ollama /api/chat со схемой (только stdlib, чтобы скрипты запускались без зависимостей).

format = JSON Schema -> Ollama/llama.cpp превращает её в грамматику (GBNF); `enum` у строк соблюдается
на уровне декодирования: токены вне списка просто недоступны модели.
NB (ресёрч): есть сообщения, что на части версий Ollama format игнорируется при think=false у qwen3.5 —
поэтому ответ всё равно валидируется, а нарушения схемы считаются в метриках (schema_violations).
"""
import json
import os
import time
import urllib.request
from dataclasses import dataclass, field


@dataclass
class CallStats:
    calls: int = 0
    prompt_tokens: int = 0
    gen_tokens: int = 0
    seconds: float = 0.0
    schema_violations: int = 0
    errors: int = 0

    def add(self, other: "CallStats") -> None:
        for k in vars(self):
            setattr(self, k, getattr(self, k) + getattr(other, k))


class OllamaLLM:
    def __init__(self, model: str, num_ctx: int = 8192, temperature: float = 0.0, host: str | None = None,
                 keep_alive: str = "30m", timeout_s: float = 600.0):
        self.model, self.num_ctx, self.temperature = model, num_ctx, temperature
        self.keep_alive, self.timeout_s = keep_alive, timeout_s
        host = host or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
        self.host = (host if "://" in host else f"http://{host}").rstrip("/")
        self.stats = CallStats()

    def chat(self, system: str, user: str, schema: dict, num_predict: int = 512) -> dict | None:
        """Возвращает распарсенный JSON или None (ошибка / не JSON). Префикс system одинаков между
        вызовами одной страницы -> llama.cpp переиспользует KV-кэш, платим только за user."""
        body = {
            "model": self.model, "stream": False, "think": False, "format": schema, "keep_alive": self.keep_alive,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx, "num_predict": num_predict},
        }
        t0 = time.monotonic()
        self.stats.calls += 1
        try:
            req = urllib.request.Request(f"{self.host}/api/chat", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                data = json.loads(r.read())
        except Exception:  # noqa: BLE001 — эксперимент: считаем и идём дальше
            self.stats.errors += 1
            return None
        finally:
            self.stats.seconds += time.monotonic() - t0
        self.stats.prompt_tokens += int(data.get("prompt_eval_count") or 0)
        self.stats.gen_tokens += int(data.get("eval_count") or 0)
        try:
            return json.loads(data.get("message", {}).get("content", ""))
        except json.JSONDecodeError:
            self.stats.schema_violations += 1
            return None


@dataclass
class FakeLLM:
    """Для тестов и сухого прогона: отвечает функцией responder(system, user, schema) -> dict."""
    responder: object
    stats: CallStats = field(default_factory=CallStats)

    def chat(self, system: str, user: str, schema: dict, num_predict: int = 512) -> dict | None:
        self.stats.calls += 1
        return self.responder(system, user, schema)  # type: ignore[operator]

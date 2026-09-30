"""Pass 2, variant (b): one simple sentence -> one EDGE or PROPERTY fact, via qwen3.5:9b."""
import time
from dataclasses import dataclass

from yuzuki_local.external.ollama import LLMError, OllamaClient, PromptTooLong

from .prompt_renderer import PromptRenderer
from .schemas import ParseReply
from .settings import RosterEntry


@dataclass(frozen=True)
class ParseResult:
    parsed: ParseReply | None
    raw_response: str
    status: str
    error: str | None
    prompt_eval_count: int
    prompt_eval_ms: float
    eval_count: int
    eval_ms: float
    seconds: float


class LlmParser:
    def __init__(self, llm: OllamaClient, renderer: PromptRenderer, universe: str,
                characters: tuple[RosterEntry, ...], groups: tuple[RosterEntry, ...]):
        self._llm = llm
        self._renderer = renderer
        self._universe = universe
        self._characters = characters
        self._groups = groups

    def prompt_version(self) -> str:
        return self._renderer.template_hash("parse_prompt.j2")

    def parse(self, sentence: str, temperature: float = 0.0) -> ParseResult:
        prompt = self._renderer.parse(sentence, self._universe, self._characters, self._groups)
        t0 = time.monotonic()
        try:
            result = self._llm.chat(prompt, ParseReply, temperature)
        except PromptTooLong:
            raise
        except LLMError as e:
            return ParseResult(None, e.raw, "error", str(e), e.metrics.prompt_eval_count,
                               e.metrics.prompt_eval_ms, e.metrics.eval_count, e.metrics.eval_ms,
                               time.monotonic() - t0)
        m = result.metrics
        return ParseResult(result.parsed, result.raw, "ok", None, m.prompt_eval_count, m.prompt_eval_ms,
                           m.eval_count, m.eval_ms, time.monotonic() - t0)

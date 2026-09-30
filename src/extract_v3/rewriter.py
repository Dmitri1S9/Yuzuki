"""Pass 1: one target sentence + a small window of neighbors -> a list of simple sentences (or a single
HYPOTHETICAL marker). One LLM call per sentence."""
import time
from dataclasses import dataclass

from yuzuki_local.external.ollama import LLMError, OllamaClient, PromptTooLong

from .prompt_renderer import PromptRenderer
from .schemas import RewriteReply
from .settings import RosterEntry
from .text_prep import Sentence

WINDOW = 3  # up to 3 sentences before/after, capped by section boundaries


@dataclass(frozen=True)
class RewriteResult:
    source_id: int
    section: str
    source_text: str
    simple_sentences: tuple[str, ...]
    hypothetical: bool
    raw_response: str
    status: str
    error: str | None
    prompt_eval_count: int
    prompt_eval_ms: float
    eval_count: int
    eval_ms: float
    seconds: float


class Rewriter:
    def __init__(self, llm: OllamaClient, renderer: PromptRenderer, universe: str,
                characters: tuple[RosterEntry, ...], groups: tuple[RosterEntry, ...]):
        self._llm = llm
        self._renderer = renderer
        self._universe = universe
        self._characters = characters
        self._groups = groups

    def prompt_version(self) -> str:
        return self._renderer.template_hash("rewrite_prompt.j2")

    def rewrite(self, sentences: list[Sentence], index: int, temperature: float = 0.0) -> RewriteResult:
        target = sentences[index]
        same_section = [s for s in sentences if s.section == target.section]
        pos = same_section.index(target)
        before = " ".join(s.text for s in same_section[max(0, pos - WINDOW):pos])
        after = " ".join(s.text for s in same_section[pos + 1:pos + 1 + WINDOW])
        before = (before + " ") if before else ""
        after = (" " + after) if after else ""

        prompt = self._renderer.rewrite(target.section, before, target.text, after, self._universe,
                                        self._characters, self._groups)
        t0 = time.monotonic()
        try:
            result = self._llm.chat(prompt, RewriteReply, temperature)
        except PromptTooLong:
            raise
        except LLMError as e:
            return RewriteResult(target.id, target.section, target.text, (), False, e.raw, "error", str(e),
                                 e.metrics.prompt_eval_count, e.metrics.prompt_eval_ms, e.metrics.eval_count,
                                 e.metrics.eval_ms, time.monotonic() - t0)

        raw_list = [s.strip() for s in result.parsed.simple_sentences if s.strip()]
        hypothetical = raw_list == ["HYPOTHETICAL"]
        simple = () if hypothetical else tuple(raw_list)
        m = result.metrics
        return RewriteResult(target.id, target.section, target.text, simple, hypothetical, result.raw, "ok",
                             None, m.prompt_eval_count, m.prompt_eval_ms, m.eval_count, m.eval_ms,
                             time.monotonic() - t0)

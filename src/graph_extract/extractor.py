"""One chunk -> LLM call -> validated ACTION + DESCRIBED_AS facts. No embeddings here (done in a batch
after extraction, across the whole run)."""
import re
import time
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from yuzuki_local.external.ollama import LLMError, OllamaClient, PromptTooLong

from .chunker import Chunk
from .prompt_renderer import PromptRenderer
from .schemas import ChunkExtractionReply
from .settings import RosterEntry

_QUOTE_TRANSLATION = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTE_TRANSLATION).casefold()
    return re.sub(r"\s+", " ", text).strip()


def is_valid_source(sentence: str, chunk_text_normalized: str, threshold: float = 90.0) -> bool:
    needle = normalize(sentence)
    if not needle:
        return False
    if needle in chunk_text_normalized:
        return True
    return fuzz.partial_ratio(needle, chunk_text_normalized) >= threshold


@dataclass(frozen=True)
class ActionFact:
    subject: str
    subject_type: str
    action: str
    action_raw: str
    manner: str
    target: str
    target_type: str
    complement: str
    modality: str
    negated: bool
    source_sentence: str
    valid_source: bool
    section: str


@dataclass(frozen=True)
class TraitFact:
    character: str
    trait: str
    said_by: str
    negated: bool
    source_sentence: str
    valid_source: bool
    section: str


@dataclass(frozen=True)
class ChunkResult:
    actions: tuple[ActionFact, ...]
    traits: tuple[TraitFact, ...]
    raw_response: str
    status: str
    error: str | None
    prompt_eval_count: int
    prompt_eval_ms: float
    eval_count: int
    eval_ms: float
    seconds: float


class ActionExtractor:
    def __init__(self, llm: OllamaClient, renderer: PromptRenderer, universe: str,
                characters: tuple[RosterEntry, ...], groups: tuple[RosterEntry, ...]):
        self._llm = llm
        self._renderer = renderer
        self._universe = universe
        self._characters = characters
        self._groups = groups

    def prompt_version(self) -> str:
        return self._renderer.template_hash()

    def extract(self, chunk: Chunk, temperature: float = 0.0) -> ChunkResult:
        prompt = self._renderer.action(chunk.section, chunk.text, self._universe, self._characters, self._groups)
        t0 = time.monotonic()
        try:
            result = self._llm.chat(prompt, ChunkExtractionReply, temperature)
        except PromptTooLong:
            raise
        except LLMError as e:
            return ChunkResult((), (), e.raw, "error", str(e), e.metrics.prompt_eval_count,
                               e.metrics.prompt_eval_ms, e.metrics.eval_count, e.metrics.eval_ms,
                               time.monotonic() - t0)

        haystack = normalize(chunk.text)
        actions = tuple(
            ActionFact(a.subject.strip(), a.subject_type, a.action.strip().lower(), a.action_raw.strip(),
                      a.manner.strip(), a.target.strip(), a.target_type, a.complement.strip(), a.modality,
                      a.negated, a.source_sentence.strip(), is_valid_source(a.source_sentence, haystack),
                      chunk.section)
            for a in result.parsed.actions)
        traits = tuple(
            TraitFact(t.character.strip(), t.trait.strip().lower(), t.said_by.strip(), t.negated,
                      t.source_sentence.strip(), is_valid_source(t.source_sentence, haystack), chunk.section)
            for t in result.parsed.traits)
        m = result.metrics
        return ChunkResult(actions, traits, result.raw, "ok", None, m.prompt_eval_count, m.prompt_eval_ms,
                           m.eval_count, m.eval_ms, time.monotonic() - t0)

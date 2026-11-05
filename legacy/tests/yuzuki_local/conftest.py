import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from yuzuki_local.entities.results import CallMetrics, ChatResult  # noqa: E402


class FakeLLM:
    """Stands in for OllamaClient: returns queued parsed replies (or raises queued exceptions)."""
    def __init__(self, *replies, prompt_eval_count=100):
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.prompt_eval_count = prompt_eval_count
        self.model = "fake"
        self.num_ctx = 20480

    def chat(self, prompt, response_model, temperature=0.0, num_predict=None):
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        parsed = reply if isinstance(reply, response_model) else response_model(**reply)
        return ChatResult(parsed, parsed.model_dump_json(), CallMetrics(prompt_eval_count=self.prompt_eval_count))


class FakeEmbedder:
    """Deterministic 3-d 'embeddings': a text is embedded by keyword counts."""
    KEYS = ("fight", "love", "teach")

    def embed(self, texts, is_query=False):
        rows = np.array([[t.lower().count(k) + 0.01 for k in self.KEYS] for t in texts], dtype=np.float32)
        return rows / np.linalg.norm(rows, axis=1, keepdims=True)


@pytest.fixture
def context_text():
    return ("Kyoka Jiro is a student in Class 1-A. She plays the guitar every weekend, and she is “kind” to her "
            "friends.\nShe punched Bakugo in the face during the battle trial and he fell down.")

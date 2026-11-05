import json

import httpx
import pytest
from pydantic import BaseModel

from yuzuki_local.external.ollama import LLMError, OllamaClient, PromptTooLong


class Reply(BaseModel):
    answer: str


def _client(responses, **kw):
    calls = []

    def handler(request: httpx.Request):
        calls.append(json.loads(request.content))
        status, body = responses.pop(0)
        return httpx.Response(status, json=body)

    client = OllamaClient("m", num_ctx=1000, num_predict=100, retries=2, sleep=lambda s: None,
                          transport=httpx.MockTransport(handler), **kw)
    return client, calls


def ok(content='{"answer": "x"}', prompt_eval=50, done_reason="stop"):
    return 200, {"message": {"content": content}, "prompt_eval_count": prompt_eval, "prompt_eval_duration": 2_000_000_000,
                 "eval_count": 5, "eval_duration": 1_000_000_000, "total_duration": 3_500_000_000,
                 "load_duration": 0, "done_reason": done_reason}


def test_metrics_schema_and_temperature_are_sent():
    client, calls = _client([ok()])
    result = client.chat("hi", Reply, temperature=0)
    assert result.parsed.answer == "x"
    assert (result.metrics.prompt_eval_count, result.metrics.prompt_eval_ms, result.metrics.eval_ms) == (50, 2000, 1000)
    body = calls[0]
    assert body["format"]["properties"]["answer"] and body["options"]["temperature"] == 0 and body["think"] is False
    assert body["options"]["num_ctx"] == 1000


def test_invalid_json_is_retried_then_llm_error_carries_raw():
    client, calls = _client([ok("not json")] * 3)
    with pytest.raises(LLMError) as e:
        client.chat("hi", Reply)
    assert len(calls) == 3 and e.value.raw == "not json" and e.value.metrics.prompt_eval_count == 50


def test_cut_off_answer_is_not_retried():
    client, calls = _client([ok('{"answer": "x', done_reason="length")])
    with pytest.raises(LLMError, match="cut at num_predict"):
        client.chat("hi", Reply, num_predict=64)
    assert len(calls) == 1 and calls[0]["options"]["num_predict"] == 64


def test_prompt_that_fills_the_window_raises_prompt_too_long_without_retry():
    client, calls = _client([ok(prompt_eval=950)])
    with pytest.raises(PromptTooLong):
        client.chat("hi", Reply)
    assert len(calls) == 1


def test_think_is_dropped_when_the_server_rejects_it():
    client, calls = _client([(400, {"error": "think not supported"}), ok()])
    client.chat("hi", Reply)
    assert "think" in calls[0] and "think" not in calls[1]

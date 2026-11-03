import json

import httpx
import pytest

from proto_wiki.domain.schemas import CorefOutput
from proto_wiki.infra.ollama_client import LLMError, OllamaClient


def client(handler, **kw):
    return OllamaClient("m", ctx=1000, sleep=lambda s: None, transport=httpx.MockTransport(handler), **kw)


def ok(text="hello", **extra):
    return httpx.Response(200, json={"message": {"content": json.dumps({"text": text})}, **extra})


def test_request_shape_schema_temperature_and_think_off():
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return ok()

    assert client(handler).generate("sys", "usr", CorefOutput).text == "hello"
    body = seen[0]
    assert body["format"] == CorefOutput.model_json_schema()
    assert body["think"] is False and body["options"]["temperature"] == 0 and body["options"]["num_ctx"] == 1000
    assert body["stream"] is False


def test_think_400_is_retried_without_the_field_and_remembered():
    seen = []

    def handler(req):
        body = json.loads(req.content)
        seen.append("think" in body)
        return httpx.Response(400, json={"error": "does not support thinking"}) if "think" in body else ok()

    c = client(handler)
    assert c.generate("s", "u", CorefOutput).text == "hello"
    c.generate("s", "u", CorefOutput)
    assert seen == [True, False, False]


def test_retries_then_llmerror():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500, text="boom")

    with pytest.raises(LLMError, match="после 3 ретраев"):
        client(handler).generate("s", "u", CorefOutput)
    assert len(calls) == 4  # first attempt + 3 retries


def test_invalid_json_from_model_is_an_error_not_an_empty_value():
    def handler(req):
        return httpx.Response(200, json={"message": {"content": '{"wrong": 1}'}})

    with pytest.raises(LLMError):
        client(handler).generate("s", "u", CorefOutput)


def test_recovers_after_transient_failure():
    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        return httpx.Response(503) if state["n"] < 3 else ok("fine")

    assert client(handler).generate("s", "u", CorefOutput).text == "fine"


def test_truncated_prompt_is_an_error_without_retries():
    calls = []

    def handler(req):
        calls.append(1)
        return ok(prompt_eval_count=1000)

    with pytest.raises(LLMError, match="не поместился"):
        client(handler).generate("s", "u", CorefOutput)
    assert len(calls) == 1


def test_ctx_drops_to_16384_when_model_spills_to_cpu(caplog):
    state = {"loads": []}

    def handler(req):
        if req.url.path == "/api/chat":
            state["loads"].append(json.loads(req.content)["options"]["num_ctx"])
            return httpx.Response(200, json={})
        vram = 5 if state["loads"][-1] > 16384 else 10
        return httpx.Response(200, json={"models": [{"name": "m", "size": 10, "size_vram": vram}]})

    c = OllamaClient("m", ctx=32768, sleep=lambda s: None, transport=httpx.MockTransport(handler))
    c.ensure_loaded()
    assert c.ctx == 16384 and state["loads"] == [32768, 16384]
    assert "16384" in caplog.text

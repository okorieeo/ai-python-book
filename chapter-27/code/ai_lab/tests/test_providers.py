"""These tests run the REAL anthropic and openai SDKs against a fake HTTP server.

The current SDKs are built on the httpx2 package, so the fake transport comes from httpx2, not httpx.

No network and no API key are used. They prove the requests we send have the
right path and shape, and that we read the responses correctly.
"""
import json

import anthropic
import httpx2
import openai
import pytest

from ai_lab.providers import (
    AnthropicProvider,
    ChatRequest,
    Message,
    OpenAICompatProvider,
)


def make_anthropic(handler):
    client = anthropic.Anthropic(
        api_key="test-key", max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    return AnthropicProvider(client)


def make_openai(handler, *, base_url="https://api.example.test/v1", **kwargs):
    client = openai.OpenAI(
        api_key="test-key", base_url=base_url, max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    return OpenAICompatProvider(client, **kwargs)


def req(**kw):
    base = dict(model="claude-sonnet-5-5", messages=(Message("user", "Hello"),))
    base.update(kw)
    return ChatRequest(**base)


# ---------------- request validation ----------------
def test_system_role_inside_messages_is_rejected():
    with pytest.raises(ValueError, match="system"):
        Message("system", "be nice")


def test_empty_messages_and_bad_max_tokens_are_rejected():
    with pytest.raises(ValueError):
        ChatRequest(model="m", messages=())
    with pytest.raises(ValueError):
        ChatRequest(model="m", messages=(Message("user", "x"),), max_tokens=0)


# ---------------- Anthropic ----------------
ANTHROPIC_REPLY = {
    "id": "msg_01", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
    "content": [
        {"type": "thinking", "thinking": "Let me think.", "signature": "sig"},
        {"type": "text", "text": "Hi "},
        {"type": "text", "text": "there!"},
    ],
    "stop_reason": "end_turn", "stop_sequence": None,
    "usage": {"input_tokens": 12, "output_tokens": 30, "cache_creation_input_tokens": 0,
              "cache_read_input_tokens": 500},
}


def test_anthropic_request_shape_and_response_parsing():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json=ANTHROPIC_REPLY)

    provider = make_anthropic(handler)
    result = provider.complete(req(system="You are terse.", effort="low", max_tokens=256))

    assert seen["path"] == "/v1/messages"
    # The SDK sends the key as a bearer token. The older x-api-key header is still accepted by the API.
    assert seen["headers"]["authorization"] == "Bearer test-key"
    assert "anthropic-version" in seen["headers"]
    body = seen["body"]
    assert body["model"] == "claude-sonnet-5-5"
    assert body["max_tokens"] == 256
    assert body["system"] == "You are terse."
    assert body["messages"] == [{"role": "user", "content": "Hello"}]
    assert body["output_config"] == {"effort": "low"}
    # The current Claude 5.x models reject sampling parameters, so we never send them.
    assert not {"temperature", "top_p", "top_k"} & set(body)

    assert result.text == "Hi there!"  # thinking block skipped, text blocks joined
    assert result.stop_reason == "end_turn"
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 30
    assert result.usage.cache_read_tokens == 500
    assert result.provider == "anthropic"
    assert not result.was_cut_off


def test_anthropic_omits_optional_fields_when_not_set():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json=ANTHROPIC_REPLY)

    make_anthropic(handler).complete(req())
    assert "system" not in seen["body"]
    assert "output_config" not in seen["body"]


def test_anthropic_max_tokens_stop_reason_is_flagged():
    reply = dict(ANTHROPIC_REPLY, stop_reason="max_tokens", content=[{"type": "text", "text": "Cut"}])
    result = make_anthropic(lambda r: httpx2.Response(200, json=reply)).complete(req())
    assert result.was_cut_off


def test_anthropic_api_errors_surface_as_sdk_exceptions():
    def handler(request):
        return httpx2.Response(400, json={"type": "error", "error": {"type": "invalid_request_error",
                                                                      "message": "bad parameter"}})

    with pytest.raises(anthropic.BadRequestError):
        make_anthropic(handler).complete(req())


def sse(*events):
    out = ""
    for name, data in events:
        out += f"event: {name}\ndata: {json.dumps(data)}\n\n"
    return out.encode()


def test_anthropic_streaming_yields_text_then_final_completion():
    body = sse(
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 25, "output_tokens": 1}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": "Hel"}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": "lo!"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta",
                           "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                           "usage": {"output_tokens": 15}}),
        ("message_stop", {"type": "message_stop"}),
    )
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    chunks = list(make_anthropic(handler).stream(req()))
    assert seen["body"]["stream"] is True
    assert [c.text for c in chunks if c.text] == ["Hel", "lo!"]
    final = chunks[-1].completion
    assert final.text == "Hello!"
    assert final.stop_reason == "end_turn"
    assert final.usage.input_tokens == 25 and final.usage.output_tokens == 15


# ---------------- OpenAI-compatible ----------------
OPENAI_REPLY = {
    "id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": "gpt-test",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello!"},
                 "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1000, "completion_tokens": 20, "total_tokens": 1020,
              "prompt_tokens_details": {"cached_tokens": 800}},
}


def test_openai_compat_request_shape_and_response_parsing():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json=OPENAI_REPLY)

    provider = make_openai(handler, name="openai")
    result = provider.complete(req(model="gpt-test", system="Be brief.", max_tokens=300))

    assert seen["path"] == "/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    assert body["messages"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Hello"},
    ]
    assert body["max_completion_tokens"] == 300
    assert "max_tokens" not in body

    assert result.text == "Hello!"
    assert result.stop_reason == "stop"
    assert result.usage.input_tokens == 200      # 1000 prompt - 800 cached
    assert result.usage.cache_read_tokens == 800
    assert result.usage.output_tokens == 20
    assert result.provider == "openai"


def test_local_server_style_uses_max_tokens_and_a_local_base_url():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json=OPENAI_REPLY)

    provider = make_openai(handler, base_url="http://localhost:11434/v1", name="local",
                           token_param="max_tokens")
    provider.complete(req(model="some-local-model", max_tokens=64))
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert seen["body"]["max_tokens"] == 64
    assert "max_completion_tokens" not in seen["body"]


def test_openai_length_finish_reason_is_flagged_as_cut_off():
    reply = json.loads(json.dumps(OPENAI_REPLY))
    reply["choices"][0]["finish_reason"] = "length"
    result = make_openai(lambda r: httpx2.Response(200, json=reply)).complete(req(model="m"))
    assert result.was_cut_off


def test_openai_streaming_collects_text_and_usage():
    def line(obj):
        return f"data: {json.dumps(obj)}\n\n"

    base = {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": "gpt-test"}
    body = (
        line({**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hi"},
                                   "finish_reason": None}]})
        + line({**base, "choices": [{"index": 0, "delta": {"content": " there"}, "finish_reason": None}]})
        + line({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
        + line({**base, "choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 3,
                                                  "total_tokens": 13}})
        + "data: [DONE]\n\n"
    ).encode()
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    chunks = list(make_openai(handler).stream(req(model="gpt-test")))
    assert seen["body"]["stream"] is True
    assert seen["body"]["stream_options"] == {"include_usage": True}
    assert [c.text for c in chunks if c.text] == ["Hi", " there"]
    final = chunks[-1].completion
    assert final.text == "Hi there"
    assert final.stop_reason == "stop"
    assert (final.usage.input_tokens, final.usage.output_tokens) == (10, 3)

"""A fake Claude API: scripted replies, and a record of every request the agent sends.

The real anthropic SDK is used, pointed at a fake HTTP transport (httpx2, which
the current SDKs are built on). No network and no API key are needed. The tests
and the walkthrough both use it.
"""
import json

import anthropic
import httpx2


def text(t):
    return {"type": "text", "text": t, "citations": None}


def tool_use(id, name, input):
    return {"type": "tool_use", "id": id, "name": name, "input": input}


def message(content, stop_reason="end_turn", in_tokens=100, out_tokens=20):
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
        "content": content, "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": in_tokens, "output_tokens": out_tokens,
                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    }


def tool_turn(*calls, **kw):
    """A reply that asks for tools: calls are (id, name, input) tuples."""
    return message([tool_use(*c) for c in calls], stop_reason="tool_use", **kw)


class FakeAPI:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []  # the JSON body of every request, in order

    def _handler(self, request):
        self.requests.append(json.loads(request.content))
        if not self.replies:
            raise AssertionError("The agent made more API calls than the test scripted")
        return httpx2.Response(200, json=self.replies.pop(0))

    @property
    def client(self):
        return anthropic.Anthropic(
            api_key="test", max_retries=0,
            http_client=httpx2.Client(transport=httpx2.MockTransport(self._handler)),
        )

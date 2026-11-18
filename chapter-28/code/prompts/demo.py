"""Demo data for the chapter: a summary schema, test cases and a scripted stand-in model."""
import json
import re

from .evals import EvalCase, contains, is_pure_json, json_field, valid_json

SUMMARY_SCHEMA = {
    "type": "object",
    "required": ["title", "summary", "topics", "action_items"],
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 60},
        "summary": {"type": "string", "minLength": 1, "maxLength": 400},
        "topics": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
        "action_items": {"type": "array", "items": {"type": "string"}},
    },
}


def format_conversation(messages: list) -> str:
    """Turn [{"role": "user", "content": "..."}, ...] into plain 'role: text' lines."""
    return "\n".join(f"{m['role']}: {' '.join(m['content'].split())}" for m in messages)


def _case(case_id, user_text, assistant_text, keyword):
    conversation = format_conversation([
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": assistant_text},
    ])
    checks = [
        is_pure_json(),
        valid_json(SUMMARY_SCHEMA),
        json_field("title", lambda v: len(v) <= 60, "title longer than 60 characters"),
        contains(keyword),
    ]
    return EvalCase(case_id, {"conversation": conversation}, checks)


CASES = [
    _case("django_celery", "How do I retry a failed Celery task in Django?",
          "Use self.retry() inside a bound task and set max_retries.", "celery"),
    _case("double_charge", "I was charged twice for my subscription. Can you help me get a refund?",
          "I am sorry about that. Please share the date of the charges.", "charged twice"),
    _case("short_greeting", "hi", "Hello! How can I help you today?", "hi"),
    _case("react_rerender", "Why does my React component re-render every time I type in the input?",
          "State lives in the component, so each keystroke triggers a render.", "react"),
    _case("paystack_naira", "How do I accept payments in Naira with Paystack on my Django site?",
          "Initialize a transaction on the server, then verify it with the reference.", "paystack"),
    _case("long_message", "I have been trying to understand how the request lifecycle works in Django "
          "from the URL router to the template, and I keep getting confused about middleware order.",
          "Middleware wraps the view like layers of an onion.", "middleware"),
]

_TOPICS = ["celery", "django", "react", "paystack", "refund", "middleware", "naira"]


def demo_model(system: str, messages: list) -> str:
    """A scripted stand-in, NOT a real model. It copies words from the conversation.

    A prompt that says 'Return ONLY a JSON object' gets clean JSON back. A vague prompt
    gets a chatty answer, which is the failure real models often show too.
    """
    body = messages[0]["content"]
    user_lines = re.findall(r"^user: (.*)$", body, re.M)
    first = user_lines[0] if user_lines else "(empty)"
    if "Return ONLY a JSON object" not in system:
        return f'Sure! Here is a summary: the user said "{first[:40]}" and the assistant replied.'
    words = first.split()
    return json.dumps({
        "title": " ".join(words[:6]).rstrip("?.!,")[:60],
        "summary": "The user asks: " + " ".join(words[:25]),
        "topics": [t for t in _TOPICS if t in body.lower()][:5],
        "action_items": [],
    })

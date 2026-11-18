#!/usr/bin/env python3
"""
UserPromptSubmit hook: stop a prompt that contains what looks like a live secret before it is sent anywhere.
People paste an error message with the key still in it. Exit code 2 blocks the prompt and shows the message to YOU.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import guard_main  # noqa: E402

PATTERNS = {
    "an Anthropic API key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "an OpenAI-style API key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}"),
    "a live Stripe or Paystack secret key": re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{10,}"),
    "a Stripe webhook signing secret": re.compile(r"\bwhsec_[A-Za-z0-9]{16,}"),
    "an AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "a GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"),
    "a private key": re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
    "a database URL with a password": re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s:@/]+:[^\s@/]{4,}@"),
}


def find_secrets(text: str) -> list[str]:
    return [name for name, pattern in PATTERNS.items() if pattern.search(text)]


def handle(data: dict) -> int:
    found = find_secrets(str(data.get("prompt", "")))
    if found:
        sys.stderr.write(f"Prompt blocked: it looks like it contains {', '.join(found)}. "
                         "Remove it and refer to the environment variable by NAME instead (for example STRIPE_WEBHOOK_SECRET).\n")
        return 2
    return 0


if __name__ == "__main__":
    guard_main(handle)

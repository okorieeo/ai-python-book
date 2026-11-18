"""Print a run as a readable transcript. Invaluable when an agent does something odd."""
from __future__ import annotations

import json


def _short(value, limit=90) -> str:
    s = value if isinstance(value, str) else json.dumps(value)
    return s if len(s) <= limit else s[: limit - 3] + "..."


def describe_messages(messages: list[dict]) -> list[str]:
    lines = []
    for m in messages:
        who = m["role"]
        content = m["content"]
        if isinstance(content, str):
            lines.append(f"{who:<9} {_short(content)}")
            continue
        for block in content:
            kind = block.get("type")
            if kind == "text":
                lines.append(f"{who:<9} text: {_short(block['text'])}")
            elif kind == "tool_use":
                lines.append(f"{who:<9} tool_use    {block['name']} {_short(block['input'], 60)}  [{block['id']}]")
            elif kind == "tool_result":
                flag = " ERROR" if block.get("is_error") else ""
                lines.append(f"{who:<9} tool_result{flag} [{block['tool_use_id']}] {_short(block['content'], 60)}")
            else:
                lines.append(f"{who:<9} {kind} block")
    return lines

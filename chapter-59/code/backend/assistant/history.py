"""Keeping the stored conversation short without breaking it. Pure Python, no Django.

The API rejects a history in which a tool_use block is not followed by its tool_result.
So we never cut
in the middle of a turn: we cut only where the PERSON started a new message.
"""


def is_person_message(message: dict) -> bool:
    """True for something the person typed. A user message made of tool_result blocks is
    machinery."""
    return message.get("role") == "user" and (
        isinstance(message.get("content"), str)
        or any(b.get("type") == "text" for b in message["content"])
    )


def trim_history(messages: list[dict], *, keep_turns: int = 12) -> list[dict]:
    """Keep the last `keep_turns` turns. A turn begins at a person's message and
    includes everything after it."""
    starts = [i for i, m in enumerate(messages) if is_person_message(m)]
    if len(starts) <= keep_turns:
        return list(messages)
    return list(messages[starts[-keep_turns]:])


def tool_use_ids(message: dict) -> list[str]:
    content = message.get("content")
    return [b["id"] for b in content if isinstance(content, list) and b.get("type") == "tool_use"]


def history_problems(messages: list[dict]) -> list[str]:
    """Check the rule the API enforces. Used in tests and before saving: a bad history
    is worse than a short one."""
    problems = []
    for i, message in enumerate(messages):
        ids = tool_use_ids(message) if message["role"] == "assistant" else []
        if ids:
            nxt = messages[i + 1] if i + 1 < len(messages) else None
            answered = (
                [b["tool_use_id"] for b in nxt["content"] if b.get("type") == "tool_result"]
                if nxt and nxt["role"] == "user" and isinstance(nxt["content"], list) else []
            )
            if sorted(answered) != sorted(ids):
                problems.append(f"message {i}: tool_use {ids} is not answered by exactly one tool_result each")
    if messages and messages[0]["role"] != "user":
        problems.append("the history must start with a user message")
    return problems

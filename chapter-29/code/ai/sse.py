"""Server-Sent Events formatting and keep-alive. Pure Python: no Django here."""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from .dto import ServiceEvent, TextDelta, TurnFailed, TurnFinished, TurnStarted

HEARTBEAT = b": keep-alive\n\n"   # a comment line: browsers and proxies see traffic, clients ignore it


def format_event(name: str, data: dict) -> bytes:
    """
    One SSE message. json.dumps escapes newlines inside strings, so a reply containing blank
    lines cannot break the framing. (Putting raw text after `data:` would.)
    """
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {name}\ndata: {payload}\n\n".encode("utf-8")


def to_sse(event: ServiceEvent) -> bytes:
    if isinstance(event, TurnStarted):
        return format_event("start", {"user_message_id": event.user_message_id,
                                      "assistant_message_id": event.assistant_message_id})
    if isinstance(event, TextDelta):
        return format_event("delta", {"text": event.text})
    if isinstance(event, TurnFinished):
        return format_event("done", {"assistant_message_id": event.assistant_message_id,
                                     "status": event.status, "stop_reason": event.stop_reason})
    if isinstance(event, TurnFailed):
        return format_event("error", {"assistant_message_id": event.assistant_message_id, "code": event.code,
                                      "message": event.user_message, "retry_after": event.retry_after,
                                      "partial": event.partial})
    raise TypeError(f"cannot serialise {event!r}")


async def with_heartbeat(source: AsyncIterator[bytes], interval: float) -> AsyncIterator[bytes]:
    """Pass chunks through, and emit a heartbeat whenever `interval` seconds pass with nothing to send."""
    it = source.__aiter__()
    pending: asyncio.Task | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(it.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield HEARTBEAT
                continue
            try:
                chunk = pending.result()
            except StopAsyncIteration:
                return
            finally:
                pending = None
            yield chunk
    finally:
        if pending is not None:
            pending.cancel()
        aclose = getattr(it, "aclose", None)
        if aclose is not None:
            await aclose()

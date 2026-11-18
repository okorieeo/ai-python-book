"""Helpers for the two classic asyncio bugs: a task nobody is waiting for, and a call that blocks the loop."""
from __future__ import annotations

import asyncio
import logging
import time
import warnings
from contextlib import contextmanager


def describe_tasks(limit: int = 20) -> list[str]:
    """What is every task doing right now? Call this from a debug endpoint or a signal handler."""
    rows = []
    for task in list(asyncio.all_tasks())[:limit]:
        stack = task.get_stack(limit=1)
        where = f"{stack[0].f_code.co_filename.rsplit('/', 1)[-1]}:{stack[0].f_lineno}" if stack else "?"
        state = "done" if task.done() else "pending"
        rows.append(f"{task.get_name():<14} {state:<8} {task.get_coro().__qualname__:<24} at {where}")
    return rows


@contextmanager
def collect_unawaited():
    """Capture 'coroutine ... was never awaited' warnings: the signature of a forgotten await."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        found: list[str] = []
        yield found
        import gc
        gc.collect()
        found.extend(str(w.message) for w in caught if "was never awaited" in str(w.message))


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def run_with_slow_callback_detection(coro, *, threshold: float = 0.05) -> list[str]:
    """Run a coroutine in asyncio debug mode and return the 'took X seconds' warnings for blocking calls."""
    handler = _Capture()
    logger = logging.getLogger("asyncio")
    logger.addHandler(handler)
    loop = asyncio.new_event_loop()
    loop.set_debug(True)
    loop.slow_callback_duration = threshold
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()
        logger.removeHandler(handler)
    return [m for m in handler.messages if "took" in m]


def blocking_call(seconds: float) -> None:
    time.sleep(seconds)        # the bug: a synchronous sleep inside async code

"""Erase a person from every place we keep them, and prove which places succeeded."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EraseResult:
    store: str
    ok: bool
    count: int = 0
    detail: str = ""  # never put personal data in here


@dataclass
class Eraser:
    name: str
    run: Callable[[str], int]  # takes the user's public id, returns how many records it removed
    required: bool = True


@dataclass
class EraserRegistry:
    erasers: list[Eraser] = field(default_factory=list)

    def register(self, name: str, run: Callable[[str], int], *, required: bool = True) -> None:
        if any(e.name == name for e in self.erasers):
            raise ValueError(f"eraser {name!r} is already registered")
        self.erasers.append(Eraser(name, run, required))

    def names(self) -> set[str]:
        return {e.name for e in self.erasers}

    def run_all(self, subject_id: str, *, already_done: frozenset[str] = frozenset()) -> list[EraseResult]:
        """Run every eraser that has not succeeded yet. One failure never stops the others."""
        results = []
        for eraser in self.erasers:
            if eraser.name in already_done:
                continue
            try:
                count = eraser.run(subject_id)
                results.append(EraseResult(eraser.name, True, count))
            except Exception as exc:  # noqa: BLE001 - we must keep going and report
                logger.error("eraser failed", extra={"event": "eraser_failed",
                             "fields": {"store": eraser.name, "error": type(exc).__name__}})
                results.append(EraseResult(eraser.name, False, 0, type(exc).__name__))
        return results

    def is_complete(self, done: set[str]) -> bool:
        return all(e.name in done for e in self.erasers if e.required)

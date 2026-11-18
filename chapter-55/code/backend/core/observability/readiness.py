"""Readiness: can this instance really serve traffic right now?

Liveness (Chapter 51's /healthz/) asks "is the process answering?" and never touches other
services. Readiness asks "are the things I depend on working?". Standard library only; the
Django view that uses it is shown in Chapter 55.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Callable, Mapping


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    ms: int


def run_checks(checks: Mapping[str, Callable[[], None]],
               timeout: float = 2.0) -> list[CheckResult]:
    """Run every check in parallel. A check passes by returning and fails by raising.

    The whole call takes at most about `timeout` seconds, even if a check hangs: hung
    threads are abandoned, not waited for. Failure details are the exception CLASS only,
    because exception messages can contain connection strings.
    """
    if not checks:
        return []
    pool = ThreadPoolExecutor(max_workers=len(checks))
    results: list[CheckResult] = []
    try:
        started = time.monotonic()
        futures = {name: pool.submit(fn) for name, fn in checks.items()}
        deadline = started + timeout
        for name, future in futures.items():
            try:
                future.result(timeout=max(0.0, deadline - time.monotonic()))
                ok, detail = True, "ok"
            except FutureTimeout:
                ok, detail = False, f"timed out after {timeout:g}s"
            except Exception as exc:  # noqa: BLE001 - any failure means "not ready"
                ok, detail = False, type(exc).__name__
            elapsed = int((time.monotonic() - started) * 1000)
            results.append(CheckResult(name, ok, detail, elapsed))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return results


def overall_ok(results: list[CheckResult]) -> bool:
    return all(r.ok for r in results)


def public_payload(results: list[CheckResult]) -> dict:
    """What an anonymous caller (an uptime monitor) may see: nothing about internals."""
    return {"status": "ok" if overall_ok(results) else "unavailable"}


def detail_payload(results: list[CheckResult]) -> dict:
    """For logs and for staff: which check failed and how long each took."""
    return {
        "status": "ok" if overall_ok(results) else "unavailable",
        "checks": {r.name: {"ok": r.ok, "ms": r.ms, "detail": r.detail} for r in results},
    }


# ---- factories: you pass in the real connection or client ----

def database_check(connection, close_after: bool = False) -> Callable[[], None]:
    """Pass Django's `connection` with close_after=True: Django connections are per
    thread and checks run in worker threads, so each must close the one it opened."""
    def check() -> None:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        finally:
            if close_after:
                connection.close()
    return check


def redis_check(client) -> Callable[[], None]:
    def check() -> None:
        if client.ping() is not True:
            raise RuntimeError("no pong")
    return check


def queue_depth_check(client, queue: str = "celery",
                      max_depth: int = 1000) -> Callable[[], None]:
    """For ALERTING, not readiness: a long queue should page you, not pull the web app."""
    def check() -> None:
        depth = client.llen(queue)
        if depth > max_depth:
            raise RuntimeError(f"backlog {depth}")
    return check

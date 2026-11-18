"""Framework-independent health logic (Chapter 54). The Django views in health_views.py are a thin wrapper.

liveness:  "is the process running?"  Never touches the database. A failing liveness check restarts the container.
readiness: "can it do its job?"       Checks the database and Redis. A failing readiness check keeps traffic away.
Mixing the two is a classic outage: a database blip makes liveness fail and every container restarts in a loop.
"""
import concurrent.futures
from typing import Callable, Dict, Tuple


def liveness() -> Tuple[int, dict]:
    return 200, {"status": "ok"}


def readiness(checks: Dict[str, Callable[[], None]], timeout: float = 2.0) -> Tuple[int, dict]:
    """Run every check in parallel. A check passes if it returns; it fails if it raises OR takes longer than `timeout`.
    The response names the failing checks but never includes exception text (it could leak hostnames or credentials)."""
    failing = []
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(checks)))
    try:
        futures = {name: pool.submit(fn) for name, fn in checks.items()}
        for name, fut in futures.items():
            try:
                fut.result(timeout=timeout)
            except Exception:  # includes TimeoutError and anything the check raised
                failing.append(name)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    if failing:
        return 503, {"status": "unavailable", "failing": sorted(failing)}
    return 200, {"status": "ok"}

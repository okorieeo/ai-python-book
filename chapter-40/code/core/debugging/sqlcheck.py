"""Spot N+1 queries from a list of SQL strings (Django: connection.queries or CaptureQueriesContext)."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

_STRING = re.compile(r"'(?:[^']|'')*'")
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
_IN_LIST = re.compile(r"\bIN\s*\((?:\s*(?:%s|\?|\$\d+|\#)\s*,?)+\)", re.I)
_PARAM = re.compile(r"%s|\$\d+|\?")
_SPACE = re.compile(r"\s+")


def fingerprint(sql: str) -> str:
    """Same query shape, different values, gives the same fingerprint."""
    s = _STRING.sub("#", sql)
    s = _NUMBER.sub("#", s)
    s = _PARAM.sub("#", s)
    s = re.sub(r"\bIN\s*\((?:\s*#\s*,?)+\)", "IN (#)", s, flags=re.I)
    return _SPACE.sub(" ", s).strip().lower()


@dataclass(frozen=True)
class Repeat:
    fingerprint: str
    count: int


def find_repeats(queries: list[str], *, threshold: int = 5) -> list[Repeat]:
    counts = Counter(fingerprint(q) for q in queries)
    return [Repeat(fp, n) for fp, n in counts.most_common() if n >= threshold]


def verdict(queries: list[str], *, budget: int, threshold: int = 5) -> str:
    repeats = find_repeats(queries, threshold=threshold)
    if repeats:
        top = repeats[0]
        return f"N+1 suspected: {top.count} x  {top.fingerprint[:90]}"
    if len(queries) > budget:
        return f"over budget: {len(queries)} queries, expected at most {budget}"
    return "ok"

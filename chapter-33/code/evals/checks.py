"""
Deterministic graders: plain code, no model, free, instant, and they never disagree with themselves.
Use these for everything that can be checked mechanically; keep the (costly, noisy) judge for the rest.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class CheckResult:
    type: str
    passed: bool
    detail: str = ""


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _contains(out: str, value: str) -> CheckResult:
    ok = value.lower() in out.lower()
    return CheckResult("contains", ok, "" if ok else f"missing {value!r}")


def _contains_any(out: str, values: list[str]) -> CheckResult:
    ok = any(v.lower() in out.lower() for v in values)
    return CheckResult("contains_any", ok, "" if ok else f"none of {values!r} found")


def _not_contains(out: str, value: str) -> CheckResult:
    ok = value.lower() not in out.lower()
    return CheckResult("not_contains", ok, "" if ok else f"found forbidden {value!r}")


def _regex(out: str, pattern: str) -> CheckResult:
    ok = re.search(pattern, out, re.IGNORECASE | re.MULTILINE) is not None
    return CheckResult("regex", ok, "" if ok else f"no match for /{pattern}/")


def _not_regex(out: str, pattern: str) -> CheckResult:
    ok = re.search(pattern, out, re.IGNORECASE | re.MULTILINE) is None
    return CheckResult("not_regex", ok, "" if ok else f"unexpected match for /{pattern}/")


def _max_words(out: str, limit: int) -> CheckResult:
    n = len(out.split())
    return CheckResult("max_words", n <= limit, "" if n <= limit else f"{n} words > {limit}")


def _max_chars(out: str, limit: int) -> CheckResult:
    return CheckResult("max_chars", len(out) <= limit, "" if len(out) <= limit else f"{len(out)} chars > {limit}")


def _starts_with(out: str, value: str) -> CheckResult:
    ok = out.lstrip().lower().startswith(value.lower())
    return CheckResult("starts_with", ok, "" if ok else f"does not start with {value!r}")


def _load_json(out: str) -> Any:
    text = out.strip()
    if text.startswith("```"):                      # models often wrap JSON in a code fence
        text = re.sub(r"^```[a-zA-Z]*\n|\n?```$", "", text)
    return json.loads(text)


def _valid_json(out: str, _value: Any = None) -> CheckResult:
    try:
        _load_json(out)
        return CheckResult("valid_json", True)
    except ValueError as exc:
        return CheckResult("valid_json", False, f"not JSON: {exc}")


def _json_has_keys(out: str, keys: list[str]) -> CheckResult:
    try:
        data = _load_json(out)
    except ValueError as exc:
        return CheckResult("json_has_keys", False, f"not JSON: {exc}")
    if not isinstance(data, dict):
        return CheckResult("json_has_keys", False, "top level is not an object")
    missing = [k for k in keys if k not in data]
    return CheckResult("json_has_keys", not missing, "" if not missing else f"missing keys {missing}")


def _no_email(out: str, _value: Any = None) -> CheckResult:
    found = EMAIL_RE.search(out)
    return CheckResult("no_email", found is None, "" if not found else "output contains an email address")


CHECKS: dict[str, Callable[[str, Any], CheckResult]] = {
    "contains": _contains, "contains_any": _contains_any, "not_contains": _not_contains,
    "regex": _regex, "not_regex": _not_regex, "max_words": _max_words, "max_chars": _max_chars,
    "starts_with": _starts_with, "valid_json": _valid_json, "json_has_keys": _json_has_keys, "no_email": _no_email,
}


def run_check(output: str, check_type: str, value: Any = None) -> CheckResult:
    fn = CHECKS.get(check_type)
    if fn is None:
        raise KeyError(f"unknown check type {check_type!r}")
    try:
        return fn(output, value)
    except re.error as exc:                           # a bad pattern is a bad TEST, report it as a failure
        return CheckResult(check_type, False, f"invalid pattern: {exc}")

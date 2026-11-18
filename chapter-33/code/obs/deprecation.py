"""
Fail the pipeline BEFORE a model you depend on is switched off. A retired model does not degrade, it stops:
every call returns an error. Anthropic gives at least 60 days' notice for publicly released models, which is
plenty of time, but only if somebody is looking.

Run:  python -m obs.deprecation claude-sonnet-5-5 claude-haiku-5-5
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

LIFECYCLE_FILE = Path(__file__).with_name("model_lifecycle.json")
WARN_DAYS = 60
URGENT_DAYS = 30


@dataclass(frozen=True)
class Finding:
    model: str
    severity: str        # error | warn | info
    message: str


def load_lifecycle(path: Path = LIFECYCLE_FILE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def check_models(models: list[str], lifecycle: dict, today: date) -> list[Finding]:
    out: list[Finding] = []
    for model in models:
        info = lifecycle.get(model)
        if info is None:
            out.append(Finding(model, "warn", "not in model_lifecycle.json: add it, or check the name for typos"))
            continue
        replacement = f" Move to {info['replacement']}." if info.get("replacement") else ""
        retires = info.get("retires")
        if retires:
            days = (date.fromisoformat(retires) - today).days
            if days < 0:
                out.append(Finding(model, "error", f"was retired on {retires}; every call will fail.{replacement}"))
            elif days <= URGENT_DAYS:
                out.append(Finding(model, "error", f"retires in {days} days ({retires}).{replacement}"))
            elif days <= WARN_DAYS:
                out.append(Finding(model, "warn", f"retires in {days} days ({retires}).{replacement}"))
            else:
                out.append(Finding(model, "info", f"deprecated, retires {retires}.{replacement}"))
        elif info.get("status") == "deprecated":
            out.append(Finding(model, "warn", f"is deprecated with no retirement date recorded.{replacement}"))
        floor = info.get("retires_not_before")
        if floor:
            days = (date.fromisoformat(floor) - today).days
            if days < 0:
                out.append(Finding(model, "warn", f"the guaranteed-until date {floor} has passed; check the deprecations page"))
    return out


def main(argv: list[str], today: date | None = None) -> int:
    models = argv or []
    if not models:
        print("usage: python -m obs.deprecation MODEL [MODEL ...]")
        return 2
    findings = check_models(models, load_lifecycle(), today or date.today())
    for f in findings:
        print(f"{f.severity.upper():5} {f.model}: {f.message}")
    if not findings:
        print("all configured models are healthy")
    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

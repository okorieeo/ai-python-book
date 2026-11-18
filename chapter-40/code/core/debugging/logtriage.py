"""Group JSON log lines by request id and answer: what happened, in what order, and what failed first?"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field

LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


@dataclass
class Entry:
    time: str
    level: str
    event: str
    request_id: str
    fields: dict
    message: str = ""


@dataclass
class Timeline:
    request_id: str
    entries: list[Entry] = field(default_factory=list)

    @property
    def first_error(self) -> Entry | None:
        return next((e for e in self.entries if LEVELS.get(e.level, 0) >= 40), None)

    @property
    def duration_ms(self) -> float | None:
        values = [e.fields.get("duration_ms") for e in self.entries if "duration_ms" in e.fields]
        return max(values) if values else None


def parse_lines(lines) -> tuple[list[Entry], int]:
    """Returns entries and the number of lines that were not JSON (kept honest, never silently dropped)."""
    entries, skipped = [], 0
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            skipped += 1
            continue
        entries.append(Entry(str(data.get("time", "")), str(data.get("level", "INFO")).upper(), str(data.get("event", "")),
                             str(data.get("request_id", "-")), data.get("fields") or {}, str(data.get("message", ""))))
    return entries, skipped


def timelines(entries: list[Entry]) -> dict[str, Timeline]:
    grouped: dict[str, Timeline] = defaultdict(lambda: Timeline(""))
    for e in sorted(entries, key=lambda e: e.time):
        t = grouped[e.request_id]
        t.request_id = e.request_id
        t.entries.append(e)
    return dict(grouped)


def triage(lines, *, slow_ms: float = 1000.0) -> dict:
    entries, skipped = parse_lines(lines)
    tl = timelines(entries)
    failing = {rid: t for rid, t in tl.items() if t.first_error}
    slow = {rid: t for rid, t in tl.items() if (t.duration_ms or 0) >= slow_ms}
    return {
        "requests": len(tl), "skipped_non_json": skipped,
        "failing": sorted(failing), "slow": sorted(slow, key=lambda r: -(slow[r].duration_ms or 0)),
        "timelines": tl,
    }


def render(timeline: Timeline) -> str:
    rows = [f"request {timeline.request_id}"]
    for e in timeline.entries:
        extra = " ".join(f"{k}={v}" for k, v in e.fields.items())
        rows.append(f"  {e.time}  {e.level:<7} {e.event:<22} {extra}")
    return "\n".join(rows)


def main(argv=None) -> int:
    """python -m core.debugging.logtriage < logfile : summary, then a timeline for each failing request."""
    import sys
    result = triage(sys.stdin)
    print(f"{result['requests']} requests, {len(result['failing'])} failing, {len(result['slow'])} slow, "
          f"{result['skipped_non_json']} non-JSON lines skipped")
    for rid in result["failing"]:
        print()
        print(render(result["timelines"][rid]))
    return 1 if result["failing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

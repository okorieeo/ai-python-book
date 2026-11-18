"""Before you `pip install` a package an assistant suggested, check that it is real and established.

Assistants sometimes name packages that do not exist. If someone has registered that name with
malicious code, installing it runs their code on your machine. This check asks PyPI about a name
and raises flags. It cannot prove a package is safe: it only catches the obvious cases.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional


def default_fetch(url: str) -> Optional[dict]:
    """Return the JSON at url, or None for a 404."""
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


@dataclass
class PackageReport:
    name: str
    exists: bool
    summary: str = ""
    releases: int = 0
    first_release: Optional[datetime] = None
    latest_release: Optional[datetime] = None
    flags: list[str] = field(default_factory=list)


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def check_package(name: str, *, fetch: Callable[[str], Optional[dict]] = default_fetch,
                  now: Optional[datetime] = None) -> PackageReport:
    now = now or datetime.now(timezone.utc)
    data = fetch(f"https://pypi.org/pypi/{name}/json")
    if data is None:
        return PackageReport(name, False, flags=["NOT FOUND on PyPI: the name may be invented. Do not install it."])
    info, releases = data.get("info", {}), data.get("releases", {})
    times = [_parse(f["upload_time_iso_8601"]) for files in releases.values() for f in files if f.get("upload_time_iso_8601")]
    report = PackageReport(name, True, info.get("summary") or "", len([v for v, f in releases.items() if f]),
                           min(times) if times else None, max(times) if times else None)
    if report.first_release and now - report.first_release < timedelta(days=90):
        report.flags.append("Very new: the first release is less than 90 days old.")
    if report.releases <= 2:
        report.flags.append("Few releases: two or fewer.")
    if not info.get("project_urls") and not info.get("home_page"):
        report.flags.append("No project links (repository or homepage) listed.")
    if report.latest_release and now - report.latest_release > timedelta(days=730):
        report.flags.append("Not updated for over two years.")
    return report


def format_package(report: PackageReport) -> str:
    if not report.exists:
        return f"{report.name}: {report.flags[0]}"
    first = report.first_release.strftime("%Y-%m-%d") if report.first_release else "unknown"
    last = report.latest_release.strftime("%Y-%m-%d") if report.latest_release else "unknown"
    lines = [f"{report.name}: found. {report.releases} releases, first {first}, latest {last}.",
             f"  summary: {report.summary or '(none)'}"]
    lines += [f"  flag: {f}" for f in report.flags] or ["  no flags raised (that is not proof it is safe)"]
    return "\n".join(lines)

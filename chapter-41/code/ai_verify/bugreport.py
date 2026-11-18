"""Turn a failure into a report an assistant (or a colleague) can act on, without leaking secrets."""
from __future__ import annotations

import platform
import re
import sys
from importlib import metadata
from typing import Optional

# Patterns that look like secrets. This is a safety net, not a guarantee: read what you paste.
REDACTIONS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[^\s'\",;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key)(\s*[:=]\s*)(['\"]?)[^\s'\",;]+"),
     r"\1\2\3[REDACTED]"),
    (re.compile(r"(?i)\b(postgres(?:ql)?|mysql|redis|amqp)://([^:\s/@]+):([^@\s]+)@"), r"\1://\2:[REDACTED]@"),
    (re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?<!\d)\+?234[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{4}(?!\d)|(?<!\d)0[789][01]\d{8}(?!\d)"), "[REDACTED_PHONE]"),
    (re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?!\d)"), "[REDACTED_NUMBER]"),
    # Home folders carry your username.
    (re.compile(r"(/home/|/Users/)[^/\s\"']+"), r"\1[user]"),
    (re.compile(r"(?i)([A-Z]:\\Users\\)[^\\\s\"']+"), r"\1[user]"),
]


def redact(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


_FRAME = re.compile(r'^\s*File "(?P<path>[^"]+)", line (?P<line>\d+), in (?P<fn>.+)$')


def _is_library(path: str) -> bool:
    return "site-packages" in path or "dist-packages" in path or "/lib/python" in path or "\\Lib\\" in path


def trim_traceback(tb: str, *, keep_last: int = 4) -> str:
    """Keep your own frames and the last few, fold library frames, always keep the final error line."""
    lines = tb.strip().splitlines()
    if not lines:
        return ""
    frames: list[list[str]] = []
    header: list[str] = []
    tail: list[str] = []
    for i, line in enumerate(lines):
        if _FRAME.match(line):
            frames.append([line])
        elif frames and (line.startswith("    ") or line.strip().startswith("^")) and not tail:
            frames[-1].append(line)
        elif frames:
            tail = lines[i:]
            break
        else:
            header.append(line)
    if not frames:
        return "\n".join(lines)
    keep: list[list[str]] = []
    folded = 0
    for idx, f in enumerate(frames):
        m = _FRAME.match(f[0])
        own = not _is_library(m.group("path"))
        recent = idx >= len(frames) - keep_last
        if own or recent:
            if folded:
                keep.append([f"  ... ({folded} library frames not shown)"])
                folded = 0
            keep.append(f)
        else:
            folded += 1
    if folded:
        keep.append([f"  ... ({folded} library frames not shown)"])
    out = header + [l for f in keep for l in f] + tail
    return "\n".join(out)


def environment_summary(packages: tuple[str, ...] = ()) -> str:
    parts = [f"Python {platform.python_version()} on {platform.system()}"]
    for name in packages:
        try:
            parts.append(f"{name} {metadata.version(name)}")
        except metadata.PackageNotFoundError:
            parts.append(f"{name} (not installed)")
    return ", ".join(parts)


def build_bug_report(*, title: str, expected: str, actual: str, steps: str = "", traceback: str = "",
                     code: str = "", tried: str = "", constraints: str = "", packages: tuple[str, ...] = (),
                     max_chars: int = 12_000) -> str:
    """A structured report. Everything is redacted, the traceback is trimmed, and the size is bounded."""
    sections = [
        f"# {title}",
        "## Environment\n" + environment_summary(packages),
        "## What I expected\n" + expected.strip(),
        "## What happened instead\n" + actual.strip(),
    ]
    if steps.strip():
        sections.append("## Smallest way to reproduce\n" + steps.strip())
    if traceback.strip():
        sections.append("## Error (trimmed)\n```\n" + trim_traceback(traceback) + "\n```")
    if code.strip():
        sections.append("## Relevant code\n```python\n" + code.strip("\n") + "\n```")
    if tried.strip():
        sections.append("## What I already tried\n" + tried.strip())
    if constraints.strip():
        sections.append("## Constraints\n" + constraints.strip())
    sections.append(
        "## What I would like from you\n"
        "1. List the most likely causes, most likely first, and say what evidence would confirm each.\n"
        "2. Write a failing test that reproduces the problem, before proposing any fix.\n"
        "3. Propose the smallest change that makes that test pass, and say what else it could affect.\n"
        "4. Tell me which parts of your answer you could not verify from what I gave you.")
    report = redact("\n\n".join(sections))
    if len(report) > max_chars:
        report = report[: max_chars - 60].rstrip() + "\n\n[report cut to fit: send the missing part separately]"
    return report
